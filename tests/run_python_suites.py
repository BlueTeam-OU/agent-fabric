#!/usr/bin/env python3
"""The python suites of tests/run.py (and run.sh, its forwarder), up to AGENT_FABRIC_TEST_JOBS at a time.

Default: the cores; 1 is the old serial run. Each suite is independent: it
makes its own scratch under the run's TMPDIR (exported by run.sh), binds
port 0 for any socket and gives itself a HOME (test_launch_cli's
launcher TMPDIR is under that HOME, so no suite shares a fixed path).
The longest start first by the seconds in tests/suite_durations.json
({suite stem: seconds}, refreshed from a run's AGENT_FABRIC_TEST_DURATIONS file), so the last one started is a short one and not the
3-minute launcher alone at the end; a suite that file does not know starts before all of them, so a new long suite never lands at the
tail, and a missing or unreadable file gives the alphabetical order. Each suite's wall time and the gap between its process's exit and the end of
its pipe (a child that outlived it holds the pipe) are measured: the slowest are printed before the count, and
AGENT_FABRIC_TEST_DURATIONS, when it names a file, receives every record as JSON. A suite's output is buffered and printed
whole when it ends, under the "== <suite>" header the serial run printed, so
the log reads the same but in completion order. Exit status: 1 if any suite
failed, 2 for a bad AGENT_FABRIC_TEST_JOBS. The last line of stdout is
`FAILED_SUITES=<n>`, n the number of suites that exited non-zero (0 when none),
so run.py can say how many failed and not only that one did; it is not printed
for the exit 2, where nothing ran, nor when the runner itself fails or is killed
(a suite that cannot be started raises out of its worker; a signal ends the
process): a missing line is "unknown, at least one", never 0.

Two bounds keep a run from taking the machine with it: AGENT_FABRIC_TEST_JOBS is lowered, with a line on stderr, to what
the memory available now allows (SUITE_MEM_MIB each, an assumption not a measurement), and a suite still running after
AGENT_FABRIC_TEST_SUITE_TIMEOUT_S (default SUITE_TIMEOUT_S) is ended with its processes, printed with what it had written
and a line naming the budget, and counted as failed. A bad budget is the same exit 2 as a bad job count.

A stop (INT, TERM or HUP) is handled here, not left to the caller: no further suite is started, each running suite's
tree is TERMed once per process and KILLed after STOP_GRACE_S, what the running suites had written is printed under
their headers, and the exit status is 128+signal with no FAILED_SUITES line (suites never ran: unknown, not 0). The
output is buffered until a suite ends, so a runner that is killed instead of asked loses it; that is why run.py TERMs this
process first and waits.

AGENT_FABRIC_TEST_SHARD=<i>/<n> (1-based) runs only the i-th of n shards of the whole pool, suites and entries; unset is the whole
section. CI sets it per platform leg, so each of the three legs of a platform takes a third of the wall time and every suite still
runs on every platform. The split is shard_plan: the same on every runner, so no coordination. A bad value is exit 2.

Entries: run.py hands over `--entries <json [[label, argv]...]>`, commands that are not tests/test_*.py (the corpus lint, the
routing check). They are pool members like a suite: started first, buffered, printed under `== <label>`, counted in
FAILED_SUITES, bounded by the same timeout and ended by a stop. They run in the runner's environment and cwd, which are the
ones run.py gave the suites.

A caller that starts this in the background (`&`, then `wait`, as run.sh did so that a trap fires at once) hands it INT and QUIT
ignored, because bash starts an async command that way, and every suite would inherit that (test_fabric_lease_cli asserts its
command is not deaf to them). set -m would restore them but puts each job in a group of its own,
which run.sh's group-wide signals and its cleanup rely on not happening; so
the dispositions are reset here, before the first suite starts.
"""
import concurrent.futures
import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DURATIONS_FILE = os.path.join(HERE, "suite_durations.json")
DURATIONS_VARIABLE = "AGENT_FABRIC_TEST_DURATIONS"
SHARD_VARIABLE = "AGENT_FABRIC_TEST_SHARD"
# What an entry weighs when the durations file has no record under its label: an assumption, not a measurement. The file is
# {suite stem: seconds} and an entry's label is no stem; the corpus lint is about two minutes, the routing check seconds, and
# only the balance between shards depends on this, never their union.
ENTRY_ASSUMED_S = 60.0
SLOWEST_SHOWN = 15
# What one suite may take: a stated budget, not a measurement (none has been made of the peak). The slowest suite, the
# launcher's, takes about 3 minutes alone, so a suite that is still running after SUITE_TIMEOUT_S is hung, not slow; it is
# ended with everything it started and counted as failed. AGENT_FABRIC_TEST_SUITE_TIMEOUT_S states another.
SUITE_TIMEOUT_S = 900.0
# The jobs the machine's memory allows: MemAvailable over this assumed peak per suite (several suites start gpg agents,
# git repositories and servers). Unknown memory (no /proc/meminfo) bounds nothing.
SUITE_MEM_MIB = 1024
# After a stop, how long a suite's tree has to end on TERM before it is KILLed.
STOP_GRACE_S = 5.0

stopping = threading.Event()
stop_signal = 0
running: set[subprocess.Popen] = set()
running_lock = threading.Lock()


def known_durations(path: str = DURATIONS_FILE) -> dict[str, float]:
    """{suite stem: seconds}; empty when the file is missing or not that shape, which is the alphabetical order."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    def seconds(v: object) -> object:
        # A run's AGENT_FABRIC_TEST_DURATIONS record ({"wall_s": …}) is read as its wall time, so a CI artifact can replace
        # this file as it is downloaded.
        return v.get("wall_s") if isinstance(v, dict) else v
    return {k: float(s) for k, v in data.items()
            if isinstance(s := seconds(v), (int, float)) and not isinstance(s, bool)}


def ordered_suites(durations: dict[str, float] | None = None) -> list[str]:
    """Unknown suites first (a suite added since the last refresh may be the longest, and the tail is the worst place for
    it), then the known ones, longest first."""
    durations = known_durations() if durations is None else durations
    every = sorted(glob.glob(os.path.join("tests", "test_*.py")))

    def stem(path: str) -> str:
        return os.path.basename(path)[:-3]
    unknown = [p for p in every if stem(p) not in durations]
    known = sorted((p for p in every if stem(p) in durations), key=lambda p: (-durations[stem(p)], p))
    return unknown + known


def parse_shard(value: str) -> tuple[int, int] | None:
    """(i, n) of `i/n`, 1 <= i <= n; None when the value is anything else."""
    head, sep, tail = value.partition("/")
    if not (sep and head.isdigit() and tail.isdigit() and head.isascii() and tail.isascii()):
        return None
    i, n = int(head), int(tail)
    return (i, n) if 1 <= i <= n else None


def shard_plan(suites: dict[str, float | None], entries: dict[str, float], n: int) -> list[dict[str, float]]:
    """The n shards, each {member: assumed seconds}; every member of `suites` and `entries` is in exactly one.
    `suites` maps a suite's name to its seconds, None when the durations file does not know it.

    Longest processing time first: the longest known suite goes to the shard with the least total so far (ties: fewer members,
    then the lower index), so no shard waits on one that drew all the long ones. A suite the file does not know is dealt out by
    name, round-robin, whatever the totals: it may be the longest of all, and it must land in exactly one shard even
    when its length is not known. The entries go last, to the lightest shard: they are the biggest single pieces after
    the launcher's suite, and placing them after the suites lets them fill what the suites left uneven.
    The whole computation reads only its arguments, so the n runners of one platform agree without talking to each other."""
    shards: list[dict[str, float]] = [{} for _ in range(n)]

    def lightest() -> dict[str, float]:
        return min(shards, key=lambda shard: (sum(shard.values()), len(shard), shards.index(shard)))
    known = sorted(((name, sec) for name, sec in suites.items() if sec is not None), key=lambda kv: (-kv[1], kv[0]))
    for name, sec in known:
        lightest()[name] = sec
    for position, name in enumerate(sorted(name for name, sec in suites.items() if sec is None)):
        shards[position % n][name] = 0.0
    for label, sec in sorted(entries.items(), key=lambda kv: (-kv[1], kv[0])):
        lightest()[label] = sec
    return shards


def memory_bound(meminfo: str = "/proc/meminfo") -> int | None:
    """How many suites fit in the memory available now, at least 1; None when the kernel does not say."""
    try:
        with open(meminfo, encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return max(1, int(line.split()[1]) // 1024 // SUITE_MEM_MIB)
    except (OSError, ValueError, IndexError):
        pass
    return None


def descendants(pid: int) -> list[int]:
    """Everything below pid, from /proc. The suites are not in a group of their own (a KILL sent to the run's group must keep
    reaching them), so a suite's tree is found by walking parents."""
    kids: dict[int, list[int]] = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return []
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as fh:
                fields = fh.read().rsplit(b")", 1)[1].split()
            kids.setdefault(int(fields[1]), []).append(int(name))
        except (OSError, IndexError, ValueError):
            continue
    out: list[int] = []
    todo = [pid]
    while todo:
        for child in kids.get(todo.pop(), []):
            out.append(child)
            todo.append(child)
    return out


def run_suite(path: str, timeout_s: float, argv: list[str] | None = None) -> tuple[int, bytes, dict[str, float]]:
    """(status, output, timing). A suite past its budget is ended with its tree and reported with what it had printed and a
    line naming the budget; its status is 124, the one timeout(1) uses. `argv` is the command of an entry that is not a
    python suite. timing holds wall_s, start to the end of the pipe, and exit_to_pipe_s, the time the pipe stayed open after
    the process exited (None when the process was not seen to exit)."""
    began = time.monotonic()
    proc = subprocess.Popen(argv or [sys.executable, path], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    exited: list[float] = []
    # communicate() learns of the exit only once the pipe is closed, which is what a lingering child delays; Popen.wait
    # is safe beside it, both going through the same lock.
    threading.Thread(target=lambda: (proc.wait(), exited.append(time.monotonic())), daemon=True).start()

    def timing() -> dict[str, float]:
        ended = time.monotonic()
        return {"wall_s": round(ended - began, 2), "exit_to_pipe_s": round(max(0.0, ended - exited[0]), 2) if exited else None}
    with running_lock:
        running.add(proc)
    # A stop that came between the start and the registration found nothing to end: it is ended here.
    if stopping.is_set():
        end_trees([proc], signal.SIGTERM)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return proc.returncode, out, timing()
    except subprocess.TimeoutExpired:
        for pid in [*descendants(proc.pid), proc.pid]:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        # The pipe closes once everything holding it is dead; one that escaped the walk (a daemon) must not hang the run.
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired as hung:
            # What was read before the hang is in hand, and is the part that explains it.
            return 124, (hung.output or b"") + (f"\n{path}: still running after its {timeout_s:g} s budget; ended, and a process "
                                                 "it started still holds its pipe, so the rest of its output is lost\n").encode(), timing()
        note = f"\n{path}: still running after its {timeout_s:g} s budget; ended\n".encode()
        return 124, out + note, timing()
    finally:
        with running_lock:
            running.discard(proc)


def end_trees(procs: list[subprocess.Popen], sig: int) -> None:
    for proc in procs:
        for pid in [*descendants(proc.pid), proc.pid]:
            try:
                os.kill(pid, sig)
            except OSError:
                pass


def on_stop(signum: int, _frame: object) -> None:
    """The first signal ends the run's work; a second changes nothing (a runner's cancel sends INT, then TERM). The suites'
    trees get TERM once; whatever is still running after the grace is KILLed, so the run ends within about the grace."""
    global stop_signal
    if stopping.is_set():
        return
    stop_signal = signum
    stopping.set()
    with running_lock:
        procs = list(running)
    end_trees(procs, signal.SIGTERM)
    killer = threading.Timer(STOP_GRACE_S, lambda: end_trees(list(running), signal.SIGKILL))
    killer.daemon = True
    killer.start()


def parse_entries(argv: list[str]) -> list[tuple[str, list[str]]] | None:
    """The `--entries <json>` of run.py: [[label, [argv...]], ...]. None when it is malformed."""
    if not argv:
        return []
    try:
        if len(argv) != 2 or argv[0] != "--entries":
            return None
        entries = [(str(label), [str(a) for a in command]) for label, command in json.loads(argv[1])]
    except (ValueError, TypeError):
        return None
    return None if any(not command for _, command in entries) else entries


def slowest_report(records: dict[str, dict], shown: int = SLOWEST_SHOWN) -> str:
    rows = sorted(records.items(), key=lambda kv: (-kv[1]["wall_s"], kv[0]))[:shown]
    lines = [f"\nslowest {len(rows)} of {len(records)} (wall seconds; pipe = seconds the pipe stayed open after the process exited):"]
    for name, rec in rows:
        gap = rec["exit_to_pipe_s"]
        lines.append(f"  {rec['wall_s']:8.1f}  {name}  (pipe {'?' if gap is None else format(gap, '.1f')})")
    return "\n".join(lines)


def write_durations(path: str, records: dict[str, dict]) -> None:
    # A file that cannot be written is said, never a failed run: the records are a by-product of the verdict.
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=1, sort_keys=True)
            fh.write("\n")
    except OSError as e:
        print(f"tests/run_python_suites.py: {DURATIONS_VARIABLE}={path} cannot be written: {e.strerror}", file=sys.stderr)


def main() -> int:
    signal.signal(signal.SIGQUIT, signal.SIG_DFL)
    # SIGINT too is taken over here, which also replaces the ignored disposition a background start hands down.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, on_stop)
    os.chdir(os.path.dirname(HERE))
    entries = parse_entries(sys.argv[1:])
    if entries is None:
        print("tests/run_python_suites.py: usage: run_python_suites.py [--entries '[[label, [command...]], ...]']", file=sys.stderr)
        return 2
    slots = os.environ.get("AGENT_FABRIC_TEST_JOBS") or str(os.cpu_count() or 1)
    if not (slots.isdigit() and int(slots) >= 1):
        print(f"tests/run_python_suites.py: AGENT_FABRIC_TEST_JOBS='{slots}' is not a positive number", file=sys.stderr)
        return 2
    budget = os.environ.get("AGENT_FABRIC_TEST_SUITE_TIMEOUT_S") or str(SUITE_TIMEOUT_S)
    try:
        timeout_s = float(budget)
    except ValueError:
        timeout_s = -1.0
    if not 0 < timeout_s < float("inf"):
        print(f"tests/run_python_suites.py: AGENT_FABRIC_TEST_SUITE_TIMEOUT_S='{budget}' is not a positive number of seconds", file=sys.stderr)
        return 2
    shard = None
    if os.environ.get(SHARD_VARIABLE):
        shard = parse_shard(os.environ[SHARD_VARIABLE])
        if shard is None:
            print(f"tests/run_python_suites.py: {SHARD_VARIABLE}='{os.environ[SHARD_VARIABLE]}' is not <i>/<n> with 1 <= i <= n", file=sys.stderr)
            return 2
    fits = memory_bound()
    if fits is not None and int(slots) > fits:
        print(f"tests/run_python_suites.py: {slots} jobs would not fit the memory available ({SUITE_MEM_MIB} MiB each assumed): running {fits}",
              file=sys.stderr)
        slots = str(fits)
    printing = threading.Lock()
    failed = 0
    records: dict[str, dict] = {}

    def run(path: str, command: list[str] | None = None) -> None:
        nonlocal failed
        if stopping.is_set():
            return
        status, output, timing = run_suite(path, timeout_s, command)
        # A suite ended by INT, TERM or HUP (killed by it, or exiting 128+n) means the signal went to the whole group, and the runner's own handler is on its
        # way: the worker that got here first must not start the next suite before it has run (a group INT started a third
        # suite, MARK2, with two slots).
        if status in (-signal.SIGINT, -signal.SIGTERM, -signal.SIGHUP, 128 + signal.SIGINT, 128 + signal.SIGTERM, 128 + signal.SIGHUP):
            stopping.wait(STOP_GRACE_S)
        with printing:
            sys.stdout.write(f"\n== {path}\n")
            sys.stdout.flush()
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()
            failed += status != 0
            records[os.path.basename(path)[:-3] if command is None else path] = {**timing, "status": status}

    durations = known_durations()
    suite_paths = ordered_suites(durations)
    if shard is not None:
        index, count = shard
        stems = {path: os.path.basename(path)[:-3] for path in suite_paths}
        mine = shard_plan({path: durations.get(stem) for path, stem in stems.items()},
                          {label: durations.get(label, ENTRY_ASSUMED_S) for label, _ in entries}, count)[index - 1]
        suite_paths = [path for path in suite_paths if path in mine]
        entries = [(label, command) for label, command in entries if label in mine]
        print(f"shard {index}/{count}: {len(mine)} suites, ~{sum(mine.values()):.0f} seconds by the durations file", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(slots)) as pool:
        # Entries first: the lint alone takes about two minutes, and started last it would be the run's tail.
        futures = [pool.submit(run, label, command) for label, command in entries]
        futures += [pool.submit(run, path) for path in suite_paths]
        # A timed wait, not pool.map's untimed one: a signal Python handles only in the main thread, and a main thread
        # blocked in an untimed lock acquire runs its handler only when something wakes it — a group INT reached it 5 s late,
        # after the suites it had killed let the workers start the next ones.
        pending = set(futures)
        while pending:
            _, pending = concurrent.futures.wait(pending, timeout=0.1)
        for future in futures:
            future.result()
    if stopping.is_set():
        return 128 + stop_signal
    if records:
        print(slowest_report(records))
    if os.environ.get(DURATIONS_VARIABLE):
        write_durations(os.environ[DURATIONS_VARIABLE], records)
    # A suite's output is written whole and may end without a newline: the count starts a line of its own.
    print(f"\nFAILED_SUITES={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

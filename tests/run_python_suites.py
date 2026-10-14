#!/usr/bin/env python3
"""The python suites of tests/run.py (and run.sh, its forwarder), up to AGENT_FABRIC_TEST_JOBS at a time.

Default: the cores; 1 is the old serial run. Each suite is independent: it
makes its own scratch under the run's TMPDIR (exported by run.sh), binds
port 0 for any socket and gives itself a HOME (the one fixed path,
/var/tmp/agent-fabric-<login> in test_launch_cli, is created idempotently).
The slowest start first, so the last one started is a short one and not the
3-minute launcher alone at the end. A suite's output is buffered and printed
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

A caller that starts this in the background (`&`, then `wait`, as run.sh did so that a trap fires at once) hands it INT and QUIT
ignored, because bash starts an async command that way, and every suite would inherit that (test_fabric_lease_cli asserts its
command is not deaf to them). set -m would restore them but puts each job in a group of its own,
which run.sh's group-wide signals and its cleanup rely on not happening; so
the dispositions are reset here, before the first suite starts.
"""
import concurrent.futures
import glob
import os
import signal
import subprocess
import sys
import threading

SLOW = (
    "test_launch_cli", "test_new_agent_cli", "test_gzcoord_port", "test_bootstrap_cli",
    "test_secret_store", "test_control_agentd", "test_gzcoord_protocol", "test_jobs",
    "test_roots_readers", "test_control_ctl", "test_pr_review_status_cli", "test_arm_cli",
    "test_session_start", "test_lint", "test_assemble",
)
HERE = os.path.dirname(os.path.abspath(__file__))
# What one suite may take: a stated budget, not a measurement (none has been made of the peak). The slowest suite, the
# launcher's, takes about 3 minutes alone, so a suite that is still running after SUITE_TIMEOUT_S is hung, not slow; it is
# ended with everything it started and counted as failed. AGENT_FABRIC_TEST_SUITE_TIMEOUT_S states another.
SUITE_TIMEOUT_S = 900.0
# The jobs the machine's memory allows: MemAvailable over this assumed peak per suite (several suites start gpg agents,
# git repositories and servers). Unknown memory (no /proc/meminfo) bounds nothing.
SUITE_MEM_MIB = 1024


def ordered_suites() -> list[str]:
    every = sorted(glob.glob(os.path.join("tests", "test_*.py")))
    slow = [p for p in (os.path.join("tests", n + ".py") for n in SLOW) if p in every]
    return slow + [p for p in every if p not in slow]


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


def run_suite(path: str, timeout_s: float) -> tuple[int, bytes]:
    """(status, output). A suite past its budget is ended with its tree and reported with what it had printed and a line
    naming the budget; its status is 124, the one timeout(1) uses."""
    proc = subprocess.Popen([sys.executable, path], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return proc.returncode, out
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
                                                 "it started still holds its pipe, so the rest of its output is lost\n").encode()
        note = f"\n{path}: still running after its {timeout_s:g} s budget; ended\n".encode()
        return 124, out + note


def main() -> int:
    for sig in (signal.SIGINT, signal.SIGQUIT):
        signal.signal(sig, signal.SIG_DFL)
    os.chdir(os.path.dirname(HERE))
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
    fits = memory_bound()
    if fits is not None and int(slots) > fits:
        print(f"tests/run_python_suites.py: {slots} jobs would not fit the memory available ({SUITE_MEM_MIB} MiB each assumed): running {fits}",
              file=sys.stderr)
        slots = str(fits)
    printing = threading.Lock()
    failed = 0

    def run(path: str) -> None:
        nonlocal failed
        status, output = run_suite(path, timeout_s)
        with printing:
            sys.stdout.write(f"\n== {path}\n")
            sys.stdout.flush()
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()
            failed += status != 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=int(slots)) as pool:
        list(pool.map(run, ordered_suites()))
    # A suite's output is written whole and may end without a newline: the count starts a line of its own.
    print(f"\nFAILED_SUITES={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

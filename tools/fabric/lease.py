#!/usr/bin/env python3
"""tools/fabric/lease.py — run a command under a host-wide lease: one holder
at a time across every account on this host, by name. (ADR-040 Wave 3;
bin/fabric-lease is its shim. ADR-010 is the decision.)

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <name> [--wait SECS] [--need-mem MB] [--label JOB] -- <cmd> [args...]
            <name> --who            who holds it, if anyone
            `--wait`, `--need-mem` and `--label` take the next argument whatever
            it looks like (also `--`), or `=VALUE`; options and the name may come
            in any order before `--`; a second name, an option not listed (also
            `--help`), no name, no command after `--` (without --who) is a
            usage error. There is no help option: the usage text is what a
            usage error prints.
            The name `cpu` is a counted resource (ADR-010 A 2026-10-28), not
            a file: see CPU SLOTS below. Its own refusals end with
            reason=cpu-policy (host-load.json unreadable or invalid) or
            reason=cpu-wait (AGENT_FABRIC_CPU_WAIT not a whole number).
  env       AGENT_FABRIC_LEASES   the lease directory, /run/lock/agent-fabric
                                  when unset or empty
            AGENT_FABRIC_MEMINFO  where MemAvailable is read, /proc/meminfo
                                  when unset or empty
  stdin     not read; the command inherits it
  stdout    --who: `free: <name>` or `held: <holder record>`; the command's
            own otherwise. Nothing else.
  stderr    every refusal; the command's own. Every refusal but a usage error
            ends with ONE stable line, the contract a caller matches (ADR-010):
              fabric-lease: reason=memory|memory-unknown|timeout|held|nodir|unopenable
  exit      the command's status (128+N when a signal N killed it); 126 / 127
            when it could not be run (found but not executable / not found);
            75 (EX_TEMPFAIL) when the lease is held or memory is short;
            2 on a usage error, a missing lease directory, an unopenable
            lease file or unreadable memory; --who: 0 free, 1 held
  lock      flock(2) on <AGENT_FABRIC_LEASES>/<name>, the SAME file and the
            same kind of lock the bash took, so a bash holder and a Python
            holder exclude each other. The file is created 0666 (umask 0) when
            absent; the lock is taken on a read-only descriptor; the record
            `<login> <pid> <since> <name>[ (<label>)]` is written by a second,
            O_TRUNC-without-O_CREAT open. The descriptor is not inherited by
            the command.
  signals   TERM, INT and HUP delivered to the wrapper are forwarded to the
            command's whole process group; the wrapper waits for the command
            and exits with its status. Before the command exists they kill the
            wrapper, as they did the bash. A signal that was ignored when the
            wrapper started stays ignored and is not forwarded (bash cannot
            trap what was ignored on entry).

CPU SLOTS (ADR-010 §5 rule 9, A 2026-10-28). `cpu` is held in N slots, the
files cpu.1 … cpu.N of the lease directory, each the same flock and the same
holder record as any lease. N is policies/host-load.json for this host
(`hostname -s`), max(1, nproc // cores_per_slot) when the host has no entry;
a slot's thread budget is J = nproc // N. A taker tries each slot without
blocking, then polls every ~2 s with jitter until its wait is over: the
order of waiters is not first-come, on purpose (a queue file is more
machinery than the load observed). `fabric-lease cpu --who` prints one line
per slot and exits 0 when a slot is free, 1 when all are held, 2 when none can
be used (a slot file that cannot be opened or is not a regular file is skipped
with one stderr line naming it, in `--who` and for a taker alike); a held slot
whose recorded pid is gone ends `(orphan: a child still runs)`. `cpu` has no
`-- <cmd>` form: it is taken by the process that becomes the tool, with the
descriptor INHERITED (hold_and_exec), where every other lease's command runs
as a child with it closed. Only the shim for cargo and dotnet (cpu_shim.py) takes
a slot through acquire_cpu and hold_and_exec below; tests/run.py takes one through acquire_cpu alone
and keeps it close-on-exec in its own process, which stays the parent of its suites. The record of a slot is
`<login> <pid> <since> cpu.<k> (<label>)`; the label names the job.

WHY (every comment of the bash carried over, with the Python that now does it).

The host is one machine the accounts share, and some of what they run
is a host resource, not an account's: a backend integration suite with
its own postgres, a device emulator, a build that takes every core.
Two of those at once is how develop-qzapp died on 2026-09-19 — two
accounts started the backend suite forty seconds apart on a VM
ballooned to 8.6 GiB, 166,000 postgres files in ninety seconds, and
the VM was gone (docs/live-checks/2026-09-19-develop-qzapp-crash.md).
The fix is not a role that runs suites for everyone: it is mutual
exclusion where the suite is started (ADR-010).

A lease is a flock(2) on ${AGENT_FABRIC_LEASES:-/run/lock/agent-fabric}/<name>,
a directory every account can create files in (1777, made at boot by
the account boot script on a Qubes AppVM and by tmpfiles.d elsewhere,
both installed by tools/fabric/provisioning/persist_accounts.py). The file is
created 0666 so the holder — whichever account it is — can write one
line into it: `<login> <pid> <since> <name>`, which is what a refused
caller is told. The kernel releases the lock when the holder exits,
however it exits: a killed suite leaves no stale lease.

Fail fast by default: a session's tool call has a timeout of its own
and should decide, told who holds the lease, whether to wait, do
something else or ask; --wait SECS blocks that long first. --need-mem
refuses, lease released, when MemAvailable is under MB — the balloon
on a Qubes VM grows on demand with a lag, and a suite started at 8.6
GiB does not get its 18 before it needs them. The command runs with
the lease's descriptor closed, so nothing it spawns and leaves behind
keeps the lease. Exit status: the command's; 75 (EX_TEMPFAIL) when
the lease is held or memory is short; 2 on a usage error, a missing
lease directory, an unopenable lease file or unreadable memory.

--label names the JOB under the lease (the lease names the resource):
it rides in the holder's record, so "heavy" held by a suite says so.

What differs from the bash, on purpose:
  - the messages of a command that cannot be run are fabric-lease's own
    (`fabric-lease: <cmd>: command not found`), where bash printed its
    own with a script path and line number; the statuses are the same, and
    a command that is a bash builtin with no program of the name (`exit`)
    is still run, by bash, as `command --` did;
  - a lease file that cannot be opened says only the refusal, without the
    line bash's own failed redirection printed before it;
  - bash's job notice for a command killed by SIGKILL ("line N: PID Killed")
    is not printed;
  - the `ps` of the memory refusal is bounded (10 s), and so is the
    probe for a builtin;
  - a number past 2**63 does not wrap as bash's arithmetic did.
Bash defects replicated rather than fixed: --wait and --need-mem are read by
bash arithmetic, where a leading zero is octal and an invalid octal (08) is
an error that reads as "false" — `--need-mem 08` skips the memory check,
`--need-mem 010` is 8 MB, `--wait 08` does not wait; flock(1) is handed the
decimal text, so `--wait 010` waits ten seconds.
"""
from __future__ import annotations

import calendar
import errno
import fcntl
import json
import os
import pwd
import random
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

USAGE = """usage: fabric-lease <name> [--wait SECS] [--need-mem MB] [--label JOB] -- <cmd> [args...]
       fabric-lease <name> --who              who holds it, if anyone; exit 0 free, 1 held
"""

DEFAULT_LEASES = "/run/lock/agent-fabric"
DEFAULT_MEMINFO = "/proc/meminfo"
# A probe never holds the lock for long; a real caller waits this long
# before refusing: long enough to outlive any probe's momentary hold, far
# shorter than any real holder's seconds-to-minutes.
FAIL_FAST_S = 1
# The bash bounded neither; a hung ps or a hung probe must not hold the
# lease for good.
PS_TIMEOUT_S = 10
# setitimer's own limit is far above any wait a person asks for.
MAX_WAIT_S = 2**31 - 1
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
NUMBER_RE = re.compile(r"[0-9]+")
# Set by bin/fabric-lease when SIGPIPE was ignored on entry: Python ignores
# it at start-up and forgets what it was, and the command must get what the
# caller gave the bash.
PIPE_IGNORED_ENV = "_FABRIC_LEASE_PIPE_IGNORED"


class Exit(Exception):
    def __init__(self, code: int):
        self.code = code


def out(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def err(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


def usage() -> None:
    err(USAGE)
    raise Exit(2)


def refuse(code: int, reason: str, *msg: str) -> None:
    """The machine-readable reason, always the last line of a refusal."""
    if msg:
        err("fabric-lease: " + " ".join(msg) + "\n")
    err(f"fabric-lease: reason={reason}\n")
    raise Exit(code)


def bash_int(text: str) -> int | None:
    """What bash's (( )) makes of a string of digits: a leading zero is octal,
    and an invalid octal is an error, which an `if` reads as false."""
    if len(text) > 1 and text[0] == "0":
        try:
            return int(text, 8)
        except ValueError:
            return None
    return int(text)


class Args:
    def __init__(self) -> None:
        self.name = ""
        self.wait = "0"
        self.need = "0"
        self.who = False
        self.label = ""
        self.cmd: list[str] = []


def parse(argv: list[str]) -> Args:
    a = Args()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--wait", "--need-mem", "--label"):
            value = argv[i + 1] if i + 1 < len(argv) else ""
            i += 1
            if arg == "--wait":
                a.wait = value
            elif arg == "--need-mem":
                a.need = value
            else:
                a.label = value
        elif arg.startswith("--wait="):
            a.wait = arg[len("--wait="):]
        elif arg.startswith("--need-mem="):
            a.need = arg[len("--need-mem="):]
        elif arg.startswith("--label="):
            a.label = arg[len("--label="):]
        elif arg == "--who":
            a.who = True
        elif arg == "--":
            a.cmd = argv[i + 1:]
            break
        elif arg.startswith("-"):
            err(f"fabric-lease: unknown option {arg}\n")
            usage()
        elif a.name == "":
            a.name = arg
        else:
            err("fabric-lease: one name, then --\n")
            usage()
        i += 1
    return a


def holder(path: str) -> str:
    """The first line of the record, printable ASCII only: a record another
    login wrote by hand reaches a refused caller's terminal, control
    characters never do. O_NONBLOCK so a lease file that is a fifo cannot
    hang the read."""
    data = b""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            while len(data) < 512:
                chunk = os.read(fd, 512 - len(data))
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(fd)
    except OSError:
        pass
    first = data.split(b"\n", 1)[0]
    text = bytes(b for b in first if 0x20 <= b <= 0x7E).decode("ascii")
    return text or "(holder unrecorded)"


def login() -> str:
    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        return ""


def record(path: str, name: str, label: str) -> None:
    """Best effort, and never fatal. Written by an open WITHOUT O_CREAT:
    in a sticky world-writable directory fs.protected_regular (systemd's
    default is 1; some distributions set 2; the mechanism needs only >= 1)
    refuses an O_CREAT open of a file another login owns — found live on
    develop-qzapp, 2026-09-19, the second account locked out of the first
    one's lease file (docs/live-checks/2026-09-19-develop-qzapp-crash.md)."""
    if not os.access(path, os.W_OK, effective_ids=True):
        return
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{login()} {os.getpid()} {since} {name}{f' ({label})' if label else ''}\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_TRUNC)
        try:
            os.write(fd, line.encode("utf-8", "surrogateescape"))
        finally:
            os.close(fd)
    except OSError:
        pass


def open_lease(path: str, *, regular_only: bool = False) -> int:
    """The lease file's descriptor, the file made when absent; OSError when it
    cannot be opened. Shared with tests/run.py, which holds full-suite itself.
    regular_only (a cpu slot): the open cannot block on a fifo, and anything
    but a regular file is refused with an OSError."""
    # 0666 so a later holder, another login, can record itself; a file that
    # exists with tighter modes (made by hand) still locks, and the record is
    # best effort. The lock is taken on a READ-ONLY descriptor (see record()).
    if not os.path.exists(path):
        old = os.umask(0)
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666))
        except OSError:
            pass
        finally:
            os.umask(old)
    if not regular_only:
        return os.open(path, os.O_RDONLY)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError(errno.EINVAL, "not a regular file")
    return fd


class _Alarm(Exception):
    pass


def lock_exclusive(fd: int, seconds: int) -> bool:
    """flock -w SECS: blocks in the kernel, woken the moment the holder goes."""
    # Whether the wait ended holding the lock is the kernel's to say, not a
    # flag's: an alarm can land after flock has granted it, before any line
    # of ours runs, and read as held (75) with the lock in hand (reviews of
    # #73). On any interruption a non-blocking request on this descriptor
    # answers: it succeeds when this descriptor holds the lock already.
    def on_alarm(signum: int, frame: object) -> None:
        raise _Alarm

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, MAX_WAIT_S))
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            return True
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    except (_Alarm, OSError):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False


def mem_field(meminfo: str, key: str) -> str:
    """awk '/^KEY:/{print $2}' FILE, its output as $(...) holds it: one line
    per matching line, trailing newlines gone, an unreadable file empty."""
    try:
        with open(meminfo, "rb") as fh:
            data = fh.read().decode("latin-1")
    except OSError:
        return ""
    lines = []
    for line in data.split("\n"):
        if line.startswith(key + ":"):
            fields = line.split()
            lines.append(fields[1] if len(fields) > 1 else "")
    return "\n".join(lines).rstrip("\n")


def largest_processes() -> str:
    """The six first lines of `ps -eo user:20,pid,rss,comm --sort=-rss`,
    laid out as the bash's awk laid them; nothing when ps is not there."""
    try:
        res = subprocess.run(["ps", "-eo", "user:20,pid,rss,comm", "--sort=-rss"],
                             capture_output=True, timeout=PS_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = res.stdout.decode("utf-8", "surrogateescape").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows = []
    for n, line in enumerate(lines[:6], 1):
        if n == 1:
            rows.append("   " + line)
            continue
        f = line.split() + [""] * 4
        try:
            mb = int(float(f[2]) / 1024) if f[2] else 0
        except ValueError:
            mb = 0
        rows.append(f"   {f[0]:<20} {f[1]:>7} {mb:>6} MB {f[3]}")
    return "\n".join(rows) + "\n" if rows else ""


def check_memory(a: Args, meminfo: str) -> None:
    """Under the lease, so two callers do not both pass."""
    avail_kb = mem_field(meminfo, "MemAvailable")
    # A floor that cannot be evaluated is refused, never skipped.
    if not NUMBER_RE.fullmatch(avail_kb):
        refuse(2, "memory-unknown", f"--need-mem asked, and MemAvailable cannot be read from {meminfo}")
    avail, need = bash_int(avail_kb), bash_int(a.need)
    if avail is None or need is None or not avail // 1024 < need:
        return
    total_kb = mem_field(meminfo, "MemTotal")
    total = (bash_int(total_kb) or 0) if NUMBER_RE.fullmatch(total_kb) else 0
    err(f"fabric-lease: {a.name} needs {a.need} MB and this host has {avail // 1024} MB available "
        f"(MemTotal {total // 1024} MB) — the largest processes:\n")
    err(largest_processes())
    refuse(75, "memory")


def spawn(argv: list[str], pipe_ignored: bool) -> subprocess.Popen:
    def prepare() -> None:
        # The bash closed the lease's descriptor (9) for the command; ours is
        # close-on-exec already, and a descriptor 9 of the caller's own went
        # the same way there.
        try:
            os.close(9)
        except OSError:
            pass
        if pipe_ignored:
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    # Its own process group (the bash's `set -m`): a signal forwarded to the
    # group reaches the suite and its postgres, not the wrapper alone. Other
    # descriptors pass to the command, as in the bash, so close_fds is off.
    return subprocess.Popen(argv, close_fds=False, process_group=0, preexec_fn=prepare)


def start(argv: list[str], pipe_ignored: bool) -> subprocess.Popen | int:
    """The command's process, or the status the shell gave a command that could
    not be run, with its message."""
    name = argv[0]
    if name == "":
        err("fabric-lease: : command not found\n")
        return 127
    try:
        return spawn(argv, pipe_ignored)
    except FileNotFoundError as e:
        if "/" not in name and builtin(name):
            return spawn([bash_path(), "-c", 'command -- "$@"', "fabric-lease", *argv], pipe_ignored)
        err(f"fabric-lease: {name}: {'command not found' if '/' not in name else os.strerror(e.errno)}\n")
        return 127
    except OSError as e:
        if e.errno == errno.ENOEXEC:
            # What bash does with a program that is not an executable format:
            # runs it as a script.
            path = name if "/" in name else (shutil.which(name) or name)
            return spawn([bash_path(), path, *argv[1:]], pipe_ignored)
        # What bash names a directory given as the command, where execve says EACCES.
        reason = "Is a directory" if "/" in name and os.path.isdir(name) else os.strerror(e.errno)
        err(f"fabric-lease: {name}: {reason}\n")
        return 126


def bash_path() -> str:
    return "/bin/bash" if os.access("/bin/bash", os.X_OK) else (shutil.which("bash") or "bash")


def builtin(name: str) -> bool:
    try:
        res = subprocess.run([bash_path(), "-c", 'type -t -- "$1"', "fabric-lease", name],
                             capture_output=True, timeout=PS_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.stdout.decode("utf-8", "replace").strip() == "builtin"


def run_command(a: Args, pipe_ignored: bool, ignored_on_entry: set[int]) -> int:
    # The command runs in ITS OWN PROCESS GROUP, with the lease's descriptor
    # closed, and TERM, INT and HUP delivered to the wrapper are forwarded to
    # that whole group — a wrapper killed alone would otherwise release the
    # lease while the suite, and its postgres, were still running (the
    # re-review of 1fbed3d reproduced exactly that with the first shape of
    # this: a trap that forwarded to the direct child only, then `wait`
    # returning at once with 143). The cost: the child is not the terminal's
    # foreground group, so a command that READS THE TTY is stopped with
    # SIGTTIN — not a case for a suite started from a tool call, and the
    # reason interactive use is not what this is for.
    # The lease is held through the suite's teardown and the exit status is
    # the command's: Popen.wait is retried by Python itself when a handled
    # signal interrupts it (PEP 475), which is what the bash's repeated
    # `wait` did by hand.
    # The handlers are armed BEFORE the fork: a signal in the gap between the
    # fork and the handler would kill the wrapper with the default
    # disposition, release the lease, and leave the command running in its
    # own group — the outcome this design exists to prevent (F2). Before the
    # child exists a signal is only remembered, and forwarded once it does.
    state: dict[str, object] = {"pid": None, "pending": None}

    def forward(signum: int, frame: object = None) -> None:
        pid = state["pid"]
        if pid is None:
            state["pending"] = signum
            return
        try:
            os.killpg(pid, signum)  # type: ignore[arg-type]
        except OSError:
            pass

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        if sig not in ignored_on_entry:
            signal.signal(sig, forward)
    started = start(a.cmd, pipe_ignored)
    if isinstance(started, int):
        return started
    state["pid"] = started.pid
    if state["pending"] is not None:
        forward(state["pending"])  # type: ignore[arg-type]
    rc = started.wait()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        if sig not in ignored_on_entry:
            signal.signal(sig, signal.SIG_DFL)
    return 128 - rc if rc < 0 else rc


# --- cpu slots (ADR-010 §5 rule 9, A 2026-10-28) ------------------------------

CPU = "cpu"
POLICY_FILE = "host-load.json"
# "Every 2 s with jitter": two waiters woken by the same release must not
# keep colliding on the same instant.
CPU_POLL_S = 2.0
CPU_JITTER_S = 0.5
CPU_SAY_EVERY_S = 60
# Set in the child of a slot: a shim that finds it runs its tool directly, so
# a cargo test that runs cargo never waits on its own slot.
SLOT_ENV = "FABRIC_CPU_SLOT"
WAIT_ENV = "AGENT_FABRIC_CPU_WAIT"
OPT_OUT_ENV = "AGENT_FABRIC_CPU_LEASE"
TEST_JOBS_ENV = "AGENT_FABRIC_TEST_JOBS"
# Where host-load.json is read from, for a test and an unusual install; unset
# or empty means the copy beside this module (an installed shim) or the
# repository's policies/.
POLICY_ENV = "AGENT_FABRIC_HOST_LOAD"


@dataclass(frozen=True)
class CpuPolicy:
    host: str
    nproc: int
    slots: int
    wait_s: int

    @property
    def jobs(self) -> int:
        return max(1, self.nproc // self.slots)


@dataclass
class CpuSlot:
    """A held slot; the lock lives as long as `fd` does, so a caller keeps the
    object. The descriptor is close-on-exec: nothing the holder runs and leaves
    behind keeps the slot."""
    fd: int
    k: int
    n: int
    jobs: int
    waited_s: int

    def release(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def _whole(value: object, what: str, minimum: int) -> int:
    # bool is an int in Python, and `true` is not a count of slots.
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        refuse(2, "cpu-policy", f"{what} in {POLICY_FILE} is {json.dumps(value)}, not a whole number ≥ {minimum}")
    return value  # type: ignore[return-value]


def policy_path() -> str:
    given = os.environ.get(POLICY_ENV)
    if given:
        return given
    here = os.path.dirname(os.path.abspath(__file__))
    beside = os.path.join(here, POLICY_FILE)
    if os.path.exists(beside):
        return beside
    # Run from a working copy: the operator's policy, found as every engine
    # module finds it. Imported here because an installed copy has no roots.py.
    if here not in sys.path:
        sys.path.insert(0, here)
    import roots
    return roots.policy(POLICY_FILE)


def cpu_policy(path: str | None = None, host: str | None = None, nproc: int | None = None) -> CpuPolicy:
    """The slots and wait of this host. A host with no entry gets the default
    from cores_per_slot (the policy's own statement); a policy that cannot be
    read or is malformed is a refusal, never a guessed count: the number of
    builds a host runs at once is the owner's decision, not a fallback."""
    path = path or policy_path()
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        refuse(2, "cpu-policy", f"{path} cannot be read: {e}")
    if not isinstance(doc, dict):
        refuse(2, "cpu-policy", f"{path} is not a JSON object")
    host = host if host is not None else socket.gethostname().split(".")[0]
    nproc = nproc if nproc is not None else len(os.sched_getaffinity(0))
    hosts = doc.get("hosts", {})
    entry = hosts.get(host, {}) if isinstance(hosts, dict) else None
    if not isinstance(entry, dict):
        refuse(2, "cpu-policy", f"hosts in {path} is not a table of tables")
    per_slot = _whole(doc.get("cores_per_slot", 4), "cores_per_slot", 1)
    slots = _whole(entry["cpu_slots"], "cpu_slots", 1) if "cpu_slots" in entry else max(1, nproc // per_slot)
    return CpuPolicy(host, nproc, slots, _whole(doc.get("wait_s", 1500), "wait_s", 0))


def cpu_wait(policy: CpuPolicy) -> int:
    given = os.environ.get(WAIT_ENV)
    if not given:
        return policy.wait_s
    if not NUMBER_RE.fullmatch(given):
        refuse(2, "cpu-wait", f"{WAIT_ENV} takes whole seconds, not '{given}'")
    return int(given)


def cpu_pass_through(env: dict[str, str] | os._Environ[str] | None = None) -> str | None:
    """Why this process takes no slot, or None. Nested in a slot's child; CI (its
    runners are not shared hosts); the opt-out, which says so."""
    env = os.environ if env is None else env
    if env.get(SLOT_ENV):
        return "nested"
    if env.get("CI"):
        return "ci"
    if env.get(OPT_OUT_ENV) == "0":
        return "opt-out"
    return None


def clean_label(text: str) -> str:
    """A label rides in a file every account reads: printable ASCII, no
    parentheses (they delimit it), 40 characters."""
    return "".join(c for c in text if 0x20 <= ord(c) <= 0x7E and c not in "()")[:40].strip()


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def describe_holder(record_line: str, wall: float) -> str:
    """`<login> <label> <age>` from a holder record, whatever of it reads."""
    parts = record_line.split()
    if len(parts) < 4:
        return record_line
    label = re.search(r"\((.*)\)\s*$", record_line)
    try:
        age = " " + _age(wall - calendar.timegm(time.strptime(parts[2], "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        age = ""
    return f"{parts[0]} {label.group(1) if label else parts[3]}{age}"


def need_dir(leases: str) -> None:
    # An agent has no sudo: the directory is root's to make (the boot script,
    # tmpfiles.d, or the operator's persist run), so the message names whose
    # action it is rather than a command the caller cannot run.
    if not os.path.isdir(leases):
        refuse(2, "nodir", f"no lease directory at {leases} — it is made at boot by the fabric's "
               "provisioning; ask the host's operator (fabric-coordinator) to run fabric-host <host> persist")


def acquire_cpu(leases: str, policy: CpuPolicy, label: str, wait_s: int, *,
                sleep: Callable[[float], None] = time.sleep,
                monotonic: Callable[[], float] = time.monotonic,
                wall: Callable[[], float] = time.time,
                uniform: Callable[[float, float], float] = random.uniform,
                say: Callable[[str], None] = err) -> CpuSlot:
    """A slot of `cpu`, waiting up to wait_s seconds. Raises Exit(75) when none
    came free (reason=held without a wait, reason=timeout after one), Exit(2)
    for a directory or file that cannot be used. Shared with tests/run.py,
    which holds a slot in its own process as it holds full-suite."""
    need_dir(leases)
    started = monotonic()
    next_say = started
    said = False
    unusable: set[int] = set()
    while True:
        held: list[str] = []
        for k in range(1, policy.slots + 1):
            if k in unusable:
                continue
            name = f"{CPU}.{k}"
            path = os.path.join(leases, name)
            try:
                fd = open_lease(path, regular_only=True)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BaseException:
                    os.close(fd)
                    raise
            except BlockingIOError:
                held.append(holder(path))
                continue
            except OSError as e:
                # One slot nobody can use is a lost slot, not a lost host: the
                # others still serve (review of #425, F4).
                unusable.add(k)
                say(f"fabric-lease: {path} is unusable ({e.strerror or e}); the other cpu slots serve\n")
                continue
            record(path, name, label)
            waited = int(monotonic() - started)
            if said:
                say(f"fabric-lease: cpu slot {k}/{policy.slots} after {waited}s, jobs={policy.jobs}\n")
            return CpuSlot(fd, k, policy.slots, policy.jobs, waited)
        if len(unusable) == policy.slots:
            refuse(2, "unopenable", f"no cpu slot in {leases} can be used")
        now = monotonic()
        # An unusable slot is never free to the caller, so "1/2 held" alone would
        # read as a slot to wait for (review of #425, F5).
        lost = f", {len(unusable)} unusable" if unusable else ""
        who = f"{len(held)}/{policy.slots} held{lost}: " + ", ".join(describe_holder(h, wall()) for h in held)
        if now - started >= wait_s:
            if wait_s == 0:
                refuse(75, "held", f"cpu is held ({who}) — retry later, or --wait SECS")
            refuse(75, "timeout", f"cpu still held after {wait_s}s ({who})")
        if now >= next_say:
            say(f"fabric-lease: waiting for cpu ({who})\n")
            said = True
            next_say = now + CPU_SAY_EVERY_S
        sleep(min(max(0.0, uniform(CPU_POLL_S - CPU_JITTER_S, CPU_POLL_S + CPU_JITTER_S)), started + wait_s - now))


def cpu_child_env(env: dict[str, str] | os._Environ[str], slot: CpuSlot,
                  say: Callable[[str], None] = err) -> dict[str, str]:
    """The environment of a slot's child: its thread budget (item 2) and the
    switches that keep a long-lived build server from inheriting the slot and
    holding it for good (item 6). A CARGO_BUILD_JOBS or DOTNET_PROCESSOR_COUNT the caller
    set lower is kept and any other value is replaced, silently. TEST_JOBS_ENV
    differs: empty or unset becomes the slot's jobs, a number above them is
    lowered with a line, and everything else is kept, 0 and non-numbers
    included, because the suite that reads it owns what those mean. The slot's
    share is the point."""
    j = str(slot.jobs)
    out = dict(env)
    for var in ("CARGO_BUILD_JOBS", "DOTNET_PROCESSOR_COUNT"):
        have = out.get(var, "")
        # Empty, 0 and junk are no bound a caller chose; the length cap keeps
        # int() off a digit string past its conversion limit.
        lower = NUMBER_RE.fullmatch(have) is not None and len(have) < 10 and 0 < int(have) < slot.jobs
        out[var] = have if lower else j
    out[SLOT_ENV] = f"{slot.k}/{slot.n}"
    out["MSBUILDDISABLENODEREUSE"] = "1"
    out["UseSharedCompilation"] = "false"
    out["DOTNET_CLI_USE_MSBUILD_SERVER"] = "0"
    if not out.get("MAKEFLAGS"):
        out["MAKEFLAGS"] = f"-j{j}"
    have = out.get(TEST_JOBS_ENV, "")
    if not have:
        out[TEST_JOBS_ENV] = j
    # A digit string of 10 or more is above any budget; the length test keeps
    # int() off one past its conversion limit.
    elif NUMBER_RE.fullmatch(have) and (len(have) >= 10 or int(have) > slot.jobs):
        say(f"fabric-lease: {TEST_JOBS_ENV}={have} lowered to {j} (cpu slot {slot.k}/{slot.n})\n")
        out[TEST_JOBS_ENV] = j
    return out


def hold_and_exec(argv: list[str], slot: CpuSlot, pipe_ignored: bool) -> int:
    """Become the tool with the slot's descriptor left inheritable. The slot
    then lives as long as the tool AND anything it starts and leaves behind:
    a KILL to this process cannot free it under a build that still burns CPU
    (the shape tests/run.py was fixed for, ADR-010 A 2026-10-19), and the
    kernel frees it when the last holder of the descriptor goes. Only a
    return means the tool could not be run: the shell's 127 / 126."""
    os.set_inheritable(slot.fd, True)
    # exec keeps what Python ignores at start-up; the tool gets what the
    # caller gave this process (SIGPIPE ignored only if the forwarder said so).
    signal.signal(signal.SIGPIPE, signal.SIG_IGN if pipe_ignored else signal.SIG_DFL)
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    try:
        os.execve(argv[0], argv, cpu_child_env(os.environ, slot))
    except FileNotFoundError:
        err(f"fabric-lease: {argv[0]}: No such file or directory\n")
        return 127
    except OSError as e:
        err(f"fabric-lease: {argv[0]}: {os.strerror(e.errno or 0)}\n")
        return 126


ORPHAN = " (orphan: a child still runs)"


def orphan(record_line: str) -> bool:
    """A held slot whose recorded process is gone: the tool ended and something
    it started still holds the descriptor, which is the point of the slot
    (hold_and_exec). A pid that is not ours to signal exists; a record that
    does not read gives no answer, so no claim."""
    parts = record_line.split()
    if len(parts) < 2 or not NUMBER_RE.fullmatch(parts[1]):
        return False
    try:
        os.kill(int(parts[1]), 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OverflowError, OSError):
        return False
    return False


def who_cpu(leases: str, policy: CpuPolicy) -> int:
    need_dir(leases)
    anyfree = False
    unusable = 0
    for k in range(1, policy.slots + 1):
        name = f"{CPU}.{k}"
        path = os.path.join(leases, name)
        try:
            fd = open_lease(path, regular_only=True)
        except OSError as e:
            unusable += 1
            err(f"fabric-lease: {path} is unusable ({e.strerror or e})\n")
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            out(f"free: {name}\n")
            anyfree = True
        except BlockingIOError:
            line = holder(path)
            out(f"held: {line}{ORPHAN if orphan(line) else ''}\n")
        except OSError as e:
            unusable += 1
            err(f"fabric-lease: {path} is unusable (cannot lock: {e.strerror or e})\n")
        finally:
            os.close(fd)
    if unusable == policy.slots:
        refuse(2, "unopenable", f"no cpu slot in {leases} can be used")
    return 0 if anyfree else 1


def run(argv: list[str]) -> int:
    ignored_on_entry = {s for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
                        if signal.getsignal(s) == signal.SIG_IGN}
    # Python handles INT itself (KeyboardInterrupt); until the command exists
    # the three kill the wrapper outright, as they did the bash.
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        if sig not in ignored_on_entry:
            signal.signal(sig, signal.SIG_DFL)
    pipe_ignored = os.environ.pop(PIPE_IGNORED_ENV, "") == "1"

    leases = os.environ.get("AGENT_FABRIC_LEASES") or DEFAULT_LEASES
    meminfo = os.environ.get("AGENT_FABRIC_MEMINFO") or DEFAULT_MEMINFO
    a = parse(argv)
    if not a.name:
        usage()
    if not NAME_RE.fullmatch(a.name):
        err(f"fabric-lease: a name is [A-Za-z0-9._-], 64 at most: '{a.name}'\n")
        return 2
    if not (NUMBER_RE.fullmatch(a.wait) and NUMBER_RE.fullmatch(a.need)):
        err("fabric-lease: --wait and --need-mem take whole numbers\n")
        return 2
    # A label is written into a file every account reads and printed to
    # every refused caller: a token, no spaces, no control characters.
    if a.label and not NAME_RE.fullmatch(a.label):
        err(f"fabric-lease: a label is [A-Za-z0-9._-], 64 at most: '{a.label}'\n")
        return 2
    if not a.who and not a.cmd:
        err("fabric-lease: a command after --\n")
        usage()
    need_dir(leases)
    if a.name == CPU:
        # Not a wrapper: a slot is held by the process that becomes the tool
        # (hold_and_exec), which this wrapper's own child, in a group of its
        # own with the descriptor closed, would not be.
        if not a.who:
            err("fabric-lease: cpu is taken by the cargo and dotnet shims and by tests/run.py; "
                "`fabric-lease cpu --who` lists its slots\n")
            usage()
        return who_cpu(leases, cpu_policy())
    path = os.path.join(leases, a.name)
    try:
        fd = open_lease(path)
    except OSError:
        refuse(2, "unopenable", f"cannot open {path}")
        return 2  # refuse raises; for the reader of the types
    # A probe is a SHARED lock, never the exclusive one: an exclusive try on a
    # free lease would take it for the probe's lifetime, and sixteen daemons
    # probing at once (fabric-ctl all host) or a --who could refuse a real
    # caller and report a stale record as the holder (the whole-range review
    # of b981d19, F1). Shared locks coexist, so two probes never see each
    # other; a holder's exclusive lock refuses a shared probe, which is the
    # answer "held".
    if a.who:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            out(f"free: {a.name}\n")
            return 0
        except OSError:
            pass
        out(f"held: {holder(path)}\n")
        return 1
    # The real caller waits a bounded second before refusing: long enough
    # to outlive any probe's momentary hold, far shorter than any real
    # holder's seconds-to-minutes, so "fail fast" holds to within a second.
    if not lock_exclusive(fd, FAIL_FAST_S):
        h = holder(path)
        wait = bash_int(a.wait)
        if wait is not None and wait > 0:
            err(f"fabric-lease: {a.name} is held by {h} — waiting up to {a.wait}s\n")
            if not lock_exclusive(fd, int(a.wait)):
                refuse(75, "timeout", f"{a.name} still held by {holder(path)} after {a.wait}s")
        else:
            refuse(75, "held", f"{a.name} is held by {h} — retry later, or --wait SECS")
    # Held. The record FIRST: a caller refused while this one is still
    # checking memory must read this holder, not the previous one (F3).
    record(path, a.name, a.label)
    # Held. Memory, checked under the lease so two callers do not both pass.
    need = bash_int(a.need)
    if need is not None and need > 0:
        check_memory(a, meminfo)
    return run_command(a, pipe_ignored, ignored_on_entry)


def main(argv: list[str] | None = None) -> int:
    # SIGPIPE stays ignored, as Python leaves it: a closed stdout raises
    # BrokenPipeError here, where restoring the default would end the process
    # without running anything after; the status is the one a killed writer
    # has (128+13).
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except Exit as e:
        return e.code
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return 141


if __name__ == "__main__":
    sys.exit(main())

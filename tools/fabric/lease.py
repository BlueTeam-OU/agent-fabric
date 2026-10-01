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
both installed by runtime/provisioning/persist-accounts.sh). The file is
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

import errno
import fcntl
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys
import time

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
    # An agent has no sudo: the directory is root's to make (the boot script,
    # tmpfiles.d, or the operator's persist run), so the message names whose
    # action it is rather than a command the caller cannot run.
    if not os.path.isdir(leases):
        refuse(2, "nodir", f"no lease directory at {leases} — it is made at boot by the fabric's "
               "provisioning; ask the host's operator (fabric-coordinator) to run bin/fabric-host <host> persist")
    path = os.path.join(leases, a.name)
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
    try:
        fd = os.open(path, os.O_RDONLY)
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

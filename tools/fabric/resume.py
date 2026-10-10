#!/usr/bin/env python3
"""tools/fabric/resume.py — bring this account's last session back, behind
bin/fabric-resume.

    fabric-resume [--print] [-- <launcher args>...]

Run in the account's own shell (after `moveto <account> --resume`, or by a
person), never inside a session. It reads the account's binding (the
session id the session-start hook last recorded), finds that session's
transcript under ~/.claude/projects/, and runs the fabric's launcher with
`--resume <id>` in the directory the session ran in (the transcript's own
`cwd`), so the harness finds it. With no binding session, no transcript or
no directory left, it starts a fresh session in the binding's working copy
and says so: a resume that cannot happen is a fresh start said, never a
failure (architect-cto's plan for Fleet Deck, 2026-10-07; the upgrade
path's relaunch made first-class).

NEVER A SECOND SESSION (docs/fleet-deck/tab-states.md, "What must hold
whatever the deck does"). It refuses to start any session, resumed or
fresh, while another one could be running on the account:
  - it first takes <state>/resume.lock: flock, exclusive, non-blocking, on
    a descriptor it opens itself and marks inheritable just before it
    execs the launcher, which therefore holds it for its own life — its
    restart wait and every session it relaunches — and never hands it to
    the harness (the launcher's Popen keeps close_fds). The kernel drops it
    when the launcher exits; there is no pid file to go stale. The pid is
    written into the file once the lock is taken, and is the launcher's
    too, since an exec keeps it. Held: refused, naming that pid, or
    "pid not yet written" in the moment between the two;
  - then the account's own session state, <state>/session-state.json, as
    runtime/control/sessions.mjs counts it: an entry in a known state
    whose recorded process is alive with its recorded start time, or that
    records no process and entered its state within NO_PROCESS_FRESH_S
    (two heartbeats, 20 min); one older than that is a probe's (a real
    session always has its claude ancestor), which nothing removes, so it
    is not counted, and said, naming it. Any such session,
    not only the binding's: the binding names the last session started,
    and one from another terminal may be older. A file that exists and
    cannot be read is refused too, never read as "no session".
The lock closes the window the check alone leaves: a session enters the
state only once it has started, so two activations seconds apart would
both pass it. A person who runs the launcher by hand bypasses both.

--print says what it would do, one line, and runs nothing; with --print,
its own or one passed to the launcher after --, no lock is taken: the lock
is read from /proc/locks, and a refusal is said as a real run says it.
Exit codes: the launcher's when it runs; 2 inside a session or for a bad
argument; 3 refused (a lock held, a session alive, its state unreadable),
said in one `fabric-resume: refused: …` line on stderr; 1 when the lock
cannot be taken for any other reason.

It chooses resume or fresh, where, and the provider: the one the
account last launched on (launch-provider.json), unless the arguments name
one; for an account that never launched, routing/profiles.json's
launch_provider for it, its role or the defaults. The launcher's own default is a fixed provider, not the account's, so
a resume without it would come back on another provider's models and bill.
Model, effort and prompt stay the launcher's.
"""
from __future__ import annotations

import datetime as dt
import errno
import fcntl
import glob
import json
import os
import re
import stat
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(FABRIC, "runtime"))
sys.path.insert(0, HERE)
import roots  # noqa: E402
import identity  # noqa: E402
import install_agent_files  # noqa: E402

# A test points this at a stub; nothing else sets it.
LAUNCHER = os.environ.get("AGENT_FABRIC_RESUME_LAUNCHER") or os.path.join(FABRIC, "runtime", "openrouter", "launch")
SCAN_LINES = 50
# The harness's session id; runtime/control/sessions.mjs SESSION_ID is the
# same pattern. Anything else in a binding is no session, never a path.
# Matched whole (fullmatch): `$` would take a trailing newline, and a
# session id is a path component (re-review of #132).
SESSION_RE = re.compile(r"[A-Za-z0-9-]{8,64}")


LOCK_FILE = "resume.lock"
SESSIONS_FILE = "session-state.json"
# The hook's states (runtime/claude-code/hooks/session-state.py); an entry
# in any other is not a session, as sessions.mjs's STATES has it.
STATES = {"working", "blocked", "idle"}
REFUSED = 3
# runtime/control/sessions.mjs NO_PROCESS_FRESH_MS: two heartbeats.
NO_PROCESS_FRESH_S = 2 * 10 * 60


class Refused(Exception):
    """`fabric-resume: refused: <message>`, exit REFUSED."""


def say(msg: str) -> None:
    print(f"fabric-resume: {msg}", file=sys.stderr)


def projects_dir() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def transcript_of(session: str) -> str | None:
    """The session's transcript, wherever its launch directory put it."""
    if not SESSION_RE.fullmatch(session):
        return None
    found = sorted(glob.glob(os.path.join(projects_dir(), "*", f"{session}.jsonl")),
                   key=lambda p: os.stat(p).st_mtime, reverse=True)
    return found[0] if found else None


def cwd_of(transcript: str) -> str | None:
    """The directory the session ran in, from its own records: --resume
    finds a session only from that directory's project."""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(SCAN_LINES), fh):
                try:
                    cwd = json.loads(line).get("cwd")
                except (ValueError, AttributeError):
                    continue
                if isinstance(cwd, str) and cwd:
                    return cwd
    except OSError:
        return None
    return None


def own_dir(path: str) -> bool:
    """A directory this account owns: the resumed session loads its
    CLAUDE.md and settings, so one another login made (a recreated /tmp
    path) is no place to resume in."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()


def profile_provider(login: str, role: str | None) -> str | None:
    """routing/profiles.json's launch_provider, nearest layer first: the
    agent's, the role's, the defaults'. Unreadable, or not the shape the
    schema gives it (a hand-edited or unmerged checkout runs this without
    the lint), is none."""
    # A test points this at a fixture; nothing else sets it.
    path = os.environ.get("AGENT_FABRIC_RESUME_PROFILES") or roots.routing_profiles(engine=FABRIC)
    try:
        with open(path, encoding="utf-8") as fh:
            prof = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(prof, dict):
        return None
    agents, roles = prof.get("agents"), prof.get("roles")
    layers = [agents.get(login) if isinstance(agents, dict) else None,
              roles.get(role or "") if isinstance(roles, dict) else None, prof.get("defaults")]
    for layer in layers:
        p = layer.get("launch_provider") if isinstance(layer, dict) else None
        # "gateway" is a transport over the anthropic column (launcher/gateway.py), not one of
        # install_agent_files' columns, so it is admitted here by name.
        if p in (*install_agent_files.PROVIDERS, "gateway"):
            return p
    return None


def last_launch_transport(record: str | None = None) -> str:
    """"gateway" when the account's last launch went through the gateway
    (launch-provider.json's `transport`, written by the launcher beside the
    provider); "" otherwise, unreadable included."""
    record = record or os.path.join(install_agent_files.fabric_writes.state_dir(), install_agent_files.LAUNCH_RECORD)
    try:
        with open(record, encoding="utf-8") as fh:
            transport = json.load(fh).get("transport")
    except (OSError, ValueError, AttributeError):
        return ""
    return transport if transport == "gateway" else ""


def provider_args(extra: list[str], binding: dict | None = None) -> list[str]:
    """The caller's --provider wins; then the account's last launch; then,
    for an account that never launched (a new agent's first activation),
    the profile's launch_provider. None of them: the launcher's default."""
    if any(a == "--provider" or a.startswith("--provider=") for a in extra):
        return []
    p = install_agent_files.last_launch_provider()
    # A session that ran through the gateway comes back through it: the record's
    # provider is the column, the transport is how it was reached.
    if p == "anthropic" and last_launch_transport() == "gateway":
        p = "gateway"
    if not p:
        b = binding if binding is not None else identity.read_binding(identity.current_agent())
        p = profile_provider(identity.current_agent(), b.get("role"))
    return ["--provider", p] if p else []


def as_int(v: object) -> object:
    """JSON's numbers as sessions.mjs reads them: 12.0 is an integer."""
    return int(v) if isinstance(v, float) and v.is_integer() else v


def records_process(pid: object) -> bool:
    pid = as_int(pid)
    return isinstance(pid, int) and not isinstance(pid, bool)


def fresh_without_process(since: object, now: float) -> bool:
    """sessions.mjs's freshWithoutProcess(): within NO_PROCESS_FRESH_S of
    `since`; a since that is not a time is not."""
    try:
        t = dt.datetime.fromisoformat(since).timestamp() if isinstance(since, str) else None
    except ValueError:
        t = None
    return t is not None and now - t <= NO_PROCESS_FRESH_S


def alive(pid: object, start: object, proc: str = "/proc") -> bool:
    """sessions.mjs's alive() for an entry that records a process: alive
    while /proc has it with the recorded start time (field 22), which tells
    a reused pid apart."""
    pid, start = as_int(pid), as_int(start)
    try:
        with open(f"{proc}/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return False
    fields = raw[raw.rfind(")") + 2:].split(" ")
    if not isinstance(start, int) or isinstance(start, bool):
        return True
    return len(fields) > 19 and fields[19] == str(start)


def live_sessions(state: str, proc: str = "/proc", now: float | None = None) -> list[str]:
    """The ids of the account's live sessions, sorted; Refused when the
    file is there and cannot be read: unknown is never "none"."""
    now = time.time() if now is None else now
    path = os.path.join(state, SESSIONS_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot tell whether a session is alive: {path} cannot be read ({exc})") from None
    sessions = doc.get("sessions") if isinstance(doc, dict) else None
    if not isinstance(sessions, dict):
        # The hook writes {"sessions": {…}} and nothing else: another shape
        # is unknown, never "no session".
        raise Refused(f"cannot tell whether a session is alive: {path} is not the session-state hook's shape")
    live = []
    for sid, e in sorted(sessions.items()):
        if not isinstance(e, dict) or e.get("state") not in STATES:
            continue
        if records_process(e.get("pid")):
            if alive(e.get("pid"), e.get("start"), proc):
                live.append(sid)
        elif fresh_without_process(e.get("since"), now):
            live.append(sid)
        else:
            say(f"session {sid} records no process and its state is older than {NO_PROCESS_FRESH_S // 60} min; "
                "not counted")
    return live


def holder(path: str) -> str:
    """The pid in the lock file, believed only when /proc/locks shows that
    pid holding it: a holder that has locked and not yet written still
    finds the last, exited holder's pid in the file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            pid = fh.read().strip()
        holding = lock_holders(path)
    except (OSError, Refused):
        pid, holding = "", set()
    return f"pid {pid}" if pid.isdigit() and int(pid) in holding else "pid not yet written"


def held_message(path: str) -> str:
    return (f"another activation holds {path} ({holder(path)}): its launcher runs a session, or waits to "
            "relaunch one")


def lock_held(path: str, locks: str = "/proc/locks") -> bool:
    """Whether any process holds a flock on path, read from /proc/locks
    without taking one: --print must never stand in a real activation's
    way, as a probe lock taken and dropped would for that instant."""
    return bool(lock_holders(path, locks))


def lock_holders(path: str, locks: str = "/proc/locks") -> set[int]:
    """The pids /proc/locks names as holding a flock on path."""
    try:
        st = os.stat(path)
        with open(locks, encoding="ascii", errors="replace") as fh:
            rows = fh.read().splitlines()
    except FileNotFoundError:
        return set()
    except OSError as exc:
        raise Refused(f"cannot tell whether {path} is held: {exc}") from None
    pids = set()
    for row in rows:
        f = row.split()
        # "1: FLOCK  ADVISORY  WRITE 1234 fd:01:5678 0 EOF"; a waiter's row
        # is "1: -> FLOCK …", and a waiter holds nothing.
        if len(f) < 6 or f[1] != "FLOCK":
            continue
        try:
            maj, mnr, ino = f[5].split(":")
            dev, pid = os.makedev(int(maj, 16), int(mnr, 16)), int(f[4])
            if int(ino) != st.st_ino:
                continue
        except ValueError:
            continue
        # The kernel names the superblock's device, which a btrfs
        # subvolume's stat does not report: then the holder's own
        # descriptors say whether it is this file (the holder is this
        # account, so they are readable).
        if dev == st.st_dev or holds_open(pid, st):
            pids.add(pid)
    return pids


def holds_open(pid: int, st: os.stat_result) -> bool:
    try:
        fds = os.listdir(f"/proc/{pid}/fd")
    except OSError:
        return False
    for fd in fds:
        try:
            other = os.stat(f"/proc/{pid}/fd/{fd}")
        except OSError:
            continue
        if (other.st_dev, other.st_ino) == (st.st_dev, st.st_ino):
            return True
    return False


def take_lock(path: str) -> int:
    """The open, locked descriptor (close-on-exec until main execs);
    Refused when another holds it, OSError when it cannot be had."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            raise Refused(held_message(path)) from None
        raise
    os.ftruncate(fd, 0)
    os.pwrite(fd, f"{os.getpid()}\n".encode(), 0)
    return fd


def refuse_live(state: str) -> None:
    live = live_sessions(state)
    if live:
        raise Refused(f"session {', '.join(live)} is alive on this account ({os.path.join(state, SESSIONS_FILE)}); "
                      "not starting another")


def plan() -> tuple[list[str], str, str]:
    """(launcher argv suffix, directory, the line that says it)."""
    binding = identity.read_binding(identity.current_agent())
    session = binding.get("session")
    session = session if isinstance(session, str) and SESSION_RE.fullmatch(session) else ""
    working_copy = str(binding.get("working_copy") or os.path.expanduser("~/projects"))
    transcript = transcript_of(session)
    cwd = cwd_of(transcript) if transcript else None
    if transcript and cwd and own_dir(cwd):
        return ["--resume", session], cwd, f"resuming session {session} in {cwd}"
    why = ("no session recorded" if not session else
           f"no transcript of session {session}" if not transcript else
           f"session {session}'s directory is gone, or not this account's")
    start = working_copy if os.path.isdir(working_copy) else os.path.expanduser("~")
    return [], start, f"{why}; starting fresh in {start}"


def main(argv: list[str]) -> int:
    if os.environ.get("CLAUDECODE"):
        say("run it in the account's shell, not inside a session (it starts one)")
        return 2
    show = False
    extra: list[str] = []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--print":
            show = True
        elif a == "--":
            extra = args
            break
        elif a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            say(f"unexpected argument: {a}")
            return 2
    state = identity.agent_state_dir()
    lock_path = os.path.join(state, LOCK_FILE)
    # The launcher's own --print starts nothing either.
    dry = show or "--print" in extra
    try:
        if dry:
            if lock_held(lock_path):
                raise Refused(held_message(lock_path))
            fd = None
        else:
            os.makedirs(state, mode=0o700, exist_ok=True)
            fd = take_lock(lock_path)
        refuse_live(state)
    except Refused as exc:
        say(f"refused: {exc}")
        return REFUSED
    except OSError as exc:
        say(f"cannot take {lock_path}: {exc.strerror or exc}")
        return 1
    suffix, cwd, line = plan()
    argv = [LAUNCHER, *provider_args(extra), *extra, *suffix]
    if show:
        print(f"{line}: {' '.join(argv[1:]) or '(no arguments)'}")
        return 0
    say(line)
    os.chdir(cwd)
    if fd is not None:
        # Python opens every descriptor close-on-exec (PEP 446): without
        # this the lock would be dropped at the exec, silently.
        os.set_inheritable(fd, True)
    os.execv(LAUNCHER, argv)
    return 0  # not reached


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

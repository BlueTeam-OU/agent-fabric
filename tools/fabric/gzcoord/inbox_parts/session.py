"""tools/fabric/gzcoord/inbox_parts/session.py — the session a watch serves, and whether it is still there.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract.

WHY (2026-10-20). A session's `gzcoord-inbox --until-delivery` is a background command, and the harness does not kill a
background command when its session ends: the watch was reparented to systemd --user, kept the login's flock for its life
(watchlock.py), and the next session's watch was refused with "nothing to kill" while deliveries went to a process whose
session was gone. So a watch records the session it serves when it starts and ends when that session does, and a watch that
loses the lock to one whose session is gone ends it (watchlock.py asks here).

THE SESSION is the nearest `claude` ancestor of the watch when it has one (the harness's own process: the bash that runs the
watch outlives it), else the watch's parent. It is recorded with its start time, so a pid that was reused is another process,
not the session. A watch started with no `claude` above it and already hanging from init or from this login's systemd (a
service, a container entrypoint) is "detached": nothing above it is a session whose end could be seen, so only its parent's
death ends it. Everything is read from /proc, which takes `proc` so a test can build the tree it asks about.

Unknown stays unknown: a process /proc cannot show is not read as a live session, and a tree that cannot be read as a
reparented one is not read as orphaned, except where the session is named by a pid that is not there at all."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

PROC = "/proc"
SESSION_COMM = "claude"                   # /proc/<pid>/comm of the harness process
SHELLS = frozenset({"bash", "sh", "dash", "zsh"})   # what the harness wraps a background command in
KINDS = ("claude", "parent", "detached")
MAX_HOPS = 64


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    comm: str
    state: str
    start: str          # clock ticks since boot: with the pid, one process for the life of the machine
    uid: int


def read_proc(pid: int, proc: str = PROC) -> Proc | None:
    """What /proc/<pid>/stat and the owner of /proc/<pid> say, or None when the process is not there or cannot be read."""
    try:
        with open(f"{proc}/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        uid = os.stat(f"{proc}/{pid}").st_uid
    except (OSError, ValueError):
        return None
    # The name is in parentheses and may hold spaces and parentheses: the last `)` ends it.
    left, sep, right = text.rpartition(")")
    fields = right.split()
    if not sep or len(fields) < 20 or not fields[1].isdigit():
        return None
    return Proc(pid, int(fields[1]), left.partition("(")[2], fields[0], fields[19], uid)


def ancestors(pid: int, proc: str = PROC) -> Iterator[Proc]:
    """The parents of `pid`, nearest first, as far as /proc shows them."""
    cur = read_proc(pid, proc)
    seen = {pid}
    for _ in range(MAX_HOPS):
        if cur is None or cur.ppid <= 0 or cur.ppid in seen:
            return
        seen.add(cur.ppid)
        cur = read_proc(cur.ppid, proc)
        if cur is not None:
            yield cur


def nearest_claude(pid: int, proc: str = PROC) -> Proc | None:
    uid = os.getuid()
    return next((a for a in ancestors(pid, proc) if a.comm == SESSION_COMM and a.uid == uid), None)


def reparented(pid: int, proc: str = PROC) -> bool:
    """`pid` hangs from init, or from this login's systemd, through nothing but shells: what is left of a session's tree when
    the session's own process has gone. False for anything else, and for what /proc does not show."""
    uid = os.getuid()
    cur = read_proc(pid, proc)
    for _ in range(MAX_HOPS):
        if cur is None or cur.ppid <= 0:
            return False
        if cur.ppid == 1:
            return True
        parent = read_proc(cur.ppid, proc)
        if parent is None or parent.uid != uid:
            return False
        if parent.comm == "systemd":
            return True
        if parent.comm not in SHELLS:
            return False
        cur = parent
    return False


@dataclass(frozen=True)
class Session:
    pid: int            # the process the watch serves
    start: str          # its start time ("" when /proc did not show it)
    parent: int         # the watch's own parent when it started
    kind: str           # one of KINDS

    def fields(self) -> list[str]:
        """The lines the lock file carries after the watch's pid and start time (watchlock.py)."""
        return [str(self.pid), self.start, self.kind]

    @staticmethod
    def of(lines: list[str]) -> Session | None:
        """The session a lock file's lines name, or None for a file from a watch that recorded none (two lines)."""
        if len(lines) >= 3 and lines[0].isdigit() and lines[2] in KINDS:
            return Session(int(lines[0]), lines[1], 0, lines[2])
        return None


def current(proc: str = PROC, pid: int | None = None, ppid: int | None = None) -> Session:
    """The session of the watch this process is."""
    me = os.getpid() if pid is None else pid
    parent = os.getppid() if ppid is None else ppid
    claude = nearest_claude(me, proc)
    if claude is not None:
        return Session(claude.pid, claude.start, parent, "claude")
    p = read_proc(parent, proc)
    return Session(parent, p.start if p else "", parent, "detached" if reparented(me, proc) else "parent")


def ended(session: Session, watch: int, proc: str = PROC) -> bool:
    """Is the session gone, as seen from the watch `watch` that serves it? Gone: no such process, a zombie, another process
    under that pid; and, for a watch whose session is its parent, the watch hanging from init or systemd through shells only.
    A session /proc did not show when it was recorded (the watch is pid 1, or /proc hides its parent) has no start time, and
    what could not be seen is not seen to end: only the parent's change (`gone`) ends such a watch."""
    if not session.start:
        return False
    now = read_proc(session.pid, proc)
    if now is None or now.state == "Z" or now.start != session.start:
        return True
    return session.kind == "parent" and reparented(watch, proc)


def gone(session: Session, proc: str = PROC, pid: int | None = None, ppid: int | None = None) -> bool:
    """The watch's own question, once a second: the session ended, or the watch's parent is not the one it started under."""
    return (os.getppid() if ppid is None else ppid) != session.parent \
        or ended(session, os.getpid() if pid is None else pid, proc)


def is_inbox(pid: int, proc: str = PROC) -> bool:
    """Is `pid` a gzcoord-inbox watch (--follow or --until-delivery)? By its argv, read from /proc: the command is named
    by the script it runs (bin/gzcoord-inbox or tools/fabric/gzcoord/inbox.py) among the first words, after the interpreter
    and its flags, and a mode that takes no lock is no watch."""
    try:
        with open(f"{proc}/{pid}/cmdline", "rb") as fh:
            args = fh.read().decode("utf-8", errors="replace").split("\0")
    except OSError:
        return False
    return (any(os.path.basename(a) in ("gzcoord-inbox", "inbox.py") for a in args[:4])
            and bool({"--follow", "--until-delivery"} & set(args))
            and not {"--replay", "--history", "--held"} & set(args))

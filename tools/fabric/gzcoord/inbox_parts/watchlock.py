"""tools/fabric/gzcoord/inbox_parts/watchlock.py — one watch per login.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract.

Sessions armed a second watch by hand and then hunted it with `pkill -f`,
whose pattern also matched their own shell and the harness's tracked
watch, and the kill froze the session (2026-10-13). So the stray is made
impossible instead: --follow and --until-delivery take an exclusive flock
on a file of the login's own runtime directory, held for the process's
life. The kernel drops it when the process ends however it ends, so a
killed watch leaves no stale owner to find. The lock is about the login,
not the caller: it does not look at stdout or at who started the watch.

A WATCH THAT OUTLIVES ITS SESSION (2026-10-20) is no stale owner to the kernel: it is alive, and its flock holds. A watch ends
with its session (session.py), but one already running the code that did not, and one that has not yet noticed, would refuse
the next session's watch with "nothing to kill". So a watch that loses the lock looks at the holder: the pid /proc/locks says
holds the flock (the file's pid line when /proc/locks does not say), checked through /proc to be this login's gzcoord-inbox
watch, and, when its session is gone, ends it with SIGTERM — by that pid only, never by a pattern — waits a bounded time for the
flock, and takes over. The file carries, after the pid and the start time, the session pid, its start time and its kind
(session.py); a file of two lines is from a watch that recorded none, and is judged by whether the holder hangs from init or
systemd through shells only. A holder whose session is alive, or that is not a watch of this login, is refused as before."""
from __future__ import annotations

import fcntl
import os
import signal
import sys
import time
import urllib.parse
from typing import IO, Callable

from . import session as sess
from .hold import pid_alive

# Not through the dictionary: the line is the contract of the request that
# introduced it, and the dictionary is the coordinator's.
ALREADY_RUNNING = ("gzcoord-inbox: a watch is already running (pid {pid}, started {started}); "
                   "it ends at its next delivery, at its --deadline (default 1 h 55 min) with the quiet line, or with its session "
                   "— nothing to kill; do not run it again")
_UNKNOWN = "unknown"
# How long a watch that ended an orphan waits for its flock. SIGTERM ends a Python process at once; a holder that does not
# end in this time is a holder, refused as any other.
TAKEOVER_WAIT_S = 5.0
TAKEOVER_POLL_S = 0.05
LOCKS = "/proc/locks"


def lock_path(login: str, runtime: str | None = None) -> str:
    runtime = runtime or os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(runtime, "agent-fabric", f"gzcoord-inbox-{urllib.parse.quote(login, safe='')}.lock")


class WatchLock:
    """Held while the object lives and its file is open. `holder` is the
    (pid, started) of the watch that owns the lock when this one does not."""

    def __init__(self, path: str):
        self.path = path
        self.holder: tuple[str, str] | None = None
        self.record: list[str] = []           # every line of the file the loser read: pid, start, then the session's
        # The pid a previous watch left in the file when it is gone: the
        # kernel already freed its flock, this only lets the start say so.
        self.took_over: str | None = None
        self._fh: IO[str] | None = None

    @property
    def acquired(self) -> bool:
        return self._fh is not None

    def acquire(self, session: sess.Session | None = None) -> bool:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        # O_NOFOLLOW and no truncation on open: the file is read by the loser
        # while the winner owns it, and rewritten only once the lock is ours.
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        fh = os.fdopen(fd, "r+", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.holder = _read_holder(fh)
            self.record = _read_record(fh)
            fh.close()
            return False
        except BaseException:
            fh.close()
            raise
        # Owned from here: the pid line only tells a loser who holds it, and
        # a write that fails (a full runtime tmpfs) must not give up a lock
        # already taken. Written on the descriptor, not through `fh`: a
        # buffered line a failed flush left behind would make close() raise
        # at release, past the watch's exit codes.
        self._fh = fh
        left, _ = _read_holder(fh)
        if left.isdigit() and int(left) != os.getpid() and not pid_alive(int(left)):
            self.took_over = left
        try:
            os.ftruncate(fh.fileno(), 0)
            lines = [str(os.getpid()), time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), *(session.fields() if session else [])]
            os.pwrite(fh.fileno(), ("\n".join(lines) + "\n").encode(), 0)
        except OSError:
            pass
        return True

    def release(self) -> None:
        if self._fh is not None:
            # Emptied while the lock is still ours: a pid left in the file
            # then means the watch did not end by itself (see took_over).
            try:
                os.ftruncate(self._fh.fileno(), 0)
            except OSError:
                pass
            self._fh.close()
            self._fh = None


def _read_record(fh: IO[str]) -> list[str]:
    try:
        fh.seek(0)
        return fh.read().split("\n")[:5]
    except (OSError, ValueError):
        return []


def _read_holder(fh: IO[str]) -> tuple[str, str]:
    # The winner writes its line a moment after it takes the lock, so a
    # loser can read an empty file: that is "unknown", not a guess.
    try:
        fh.seek(0)
        pid, started = (fh.read().split("\n") + ["", ""])[:2]
    except (OSError, ValueError):
        return _UNKNOWN, _UNKNOWN
    return (pid if pid.isdigit() else _UNKNOWN), (started or _UNKNOWN)


def lock_holder(path: str, locks: str = LOCKS) -> int | None:
    """The pid /proc/locks gives as the owner of the flock on `path`, or None when it does not say (no /proc/locks, the lock
    not listed, or the owner in a pid namespace this one cannot name). The file's own pid line can be a dead watch's."""
    try:
        st = os.stat(path)
        with open(locks, encoding="ascii", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    want = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    for line in text.splitlines():
        f = line.split()
        # A waiter is `N: -> FLOCK ...`; the owner is `N: FLOCK ADVISORY WRITE <pid> <major>:<minor>:<inode> ...`.
        if len(f) >= 6 and f[1] == "FLOCK" and f[5] == want and f[4].isdigit() and int(f[4]) > 0:
            return int(f[4])
    return None


def orphan_of(path: str, record: list[str], proc: str = sess.PROC, locks: str = LOCKS) -> tuple[int, str] | None:
    """(pid, why) of the holder of the lock on `path` when it is a gzcoord-inbox watch of this login whose session is gone;
    None for every other holder, and for one that cannot be told. The pid is /proc/locks', else the file's."""
    pid = lock_holder(path, locks)
    if pid is None and record and record[0].isdigit():
        pid = int(record[0])
    if pid is None or pid == os.getpid():
        return None
    holder = sess.read_proc(pid, proc)
    if holder is None or holder.uid != os.getuid() or not sess.is_inbox(pid, proc):
        return None
    # The file's session lines are the holder's own only when its pid line is the holder's.
    recorded = sess.Session.of(record[2:]) if record[:1] == [str(pid)] else None
    if recorded is not None:
        return (pid, f"its session, pid {recorded.pid}, has ended") if sess.ended(recorded, pid, proc) else None
    return (pid, "it hangs from init or systemd through no session") if sess.reparented(pid, proc) else None


def end_orphan(path: str, record: list[str], proc: str = sess.PROC, locks: str = LOCKS,
               kill: Callable[[int, int], None] = os.kill) -> bool:
    """SIGTERM to the holder of the lock when `orphan_of` says its session is gone; True when it was sent. Said once on stderr,
    with both pids."""
    found = orphan_of(path, record, proc, locks)
    if found is None:
        return False
    pid, why = found
    print(f"gzcoord-inbox: the watch of pid {pid} outlived its session ({why}); ending it (SIGTERM) to take its place as pid {os.getpid()}",
          file=sys.stderr)
    try:
        kill(pid, signal.SIGTERM)
    except OSError:
        pass   # gone between the look and the signal: the flock is free, or it is not ours to end
    return True


def take_or_report(login: str, session: sess.Session | None = None, wait_s: float | None = None) -> WatchLock | None:
    """The lock when this process may watch; None, with the one line printed
    on stdout, when another watch of this login holds it. A lock that cannot
    be had for a local reason (no runtime directory, a read-only one) does
    not stop the watch: the guard is a convenience, the watch is the
    delivery. The reason is on stderr, said once."""
    lock = WatchLock(lock_path(login))
    try:
        if lock.acquire(session):
            if lock.took_over:
                print(f"gzcoord-inbox: taking over the watch mark of pid {lock.took_over}, which is gone", file=sys.stderr)
            return lock
        if end_orphan(lock.path, lock.record):
            until = time.monotonic() + (TAKEOVER_WAIT_S if wait_s is None else wait_s)
            while True:
                if lock.acquire(session):
                    return lock
                if time.monotonic() >= until:
                    break
                time.sleep(TAKEOVER_POLL_S)
            print("gzcoord-inbox: the orphaned watch did not release the lock in time", file=sys.stderr)
    except OSError as e:
        print(f"gzcoord-inbox: no watch lock ({lock.path}: {e.strerror or e}); watching without one", file=sys.stderr)
        return lock  # not acquired, holds nothing; release() is a no-op
    pid, started = lock.holder or (_UNKNOWN, _UNKNOWN)
    print(ALREADY_RUNNING.format(pid=pid, started=started), flush=True)
    return None

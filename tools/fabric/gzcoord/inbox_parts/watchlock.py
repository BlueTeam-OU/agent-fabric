"""tools/fabric/gzcoord/inbox_parts/watchlock.py — one watch per login.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract.

Sessions armed a second watch by hand and then hunted it with `pkill -f`,
whose pattern also matched their own shell and the harness's tracked
watch, and the kill froze the session (2026-10-13). So the stray is made
impossible instead: --follow and --until-delivery take an exclusive flock
on a file of the login's own runtime directory, held for the process's
life. The kernel drops it when the process ends however it ends, so a
killed watch leaves no stale owner to find. The lock is about the login,
not the caller: it does not look at stdout or at who started the watch."""
from __future__ import annotations

import fcntl
import os
import sys
import time
import urllib.parse
from typing import IO

# Not through the dictionary: the line is the contract of the request that
# introduced it, and the dictionary is the coordinator's.
ALREADY_RUNNING = ("gzcoord-inbox: a watch is already running (pid {pid}, started {started}); "
                   "it ends at its next delivery — nothing to kill; do not run it again")
_UNKNOWN = "unknown"


def lock_path(login: str, runtime: str | None = None) -> str:
    runtime = runtime or os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(runtime, "agent-fabric", f"gzcoord-inbox-{urllib.parse.quote(login, safe='')}.lock")


class WatchLock:
    """Held while the object lives and its file is open. `holder` is the
    (pid, started) of the watch that owns the lock when this one does not."""

    def __init__(self, path: str):
        self.path = path
        self.holder: tuple[str, str] | None = None
        self._fh: IO[str] | None = None

    @property
    def acquired(self) -> bool:
        return self._fh is not None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        # O_NOFOLLOW and no truncation on open: the file is read by the loser
        # while the winner owns it, and rewritten only once the lock is ours.
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        fh = os.fdopen(fd, "r+", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.holder = _read_holder(fh)
            fh.close()
            return False
        except BaseException:
            fh.close()
            raise
        # Owned from here: the pid line below only tells a loser who holds
        # it, and a write that fails (a full runtime tmpfs) must not give up
        # a lock already taken.
        self._fh = fh
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
            fh.flush()
        except OSError:
            pass
        return True

    def release(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _read_holder(fh: IO[str]) -> tuple[str, str]:
    # The winner writes its line a moment after it takes the lock, so a
    # loser can read an empty file: that is "unknown", not a guess.
    try:
        fh.seek(0)
        pid, started = (fh.read().split("\n") + ["", ""])[:2]
    except (OSError, ValueError):
        return _UNKNOWN, _UNKNOWN
    return (pid if pid.isdigit() else _UNKNOWN), (started or _UNKNOWN)


def take_or_report(login: str) -> WatchLock | None:
    """The lock when this process may watch; None, with the one line printed
    on stdout, when another watch of this login holds it. A lock that cannot
    be had for a local reason (no runtime directory, a read-only one) does
    not stop the watch: the guard is a convenience, the watch is the
    delivery. The reason is on stderr, said once."""
    lock = WatchLock(lock_path(login))
    try:
        if lock.acquire():
            return lock
    except OSError as e:
        print(f"gzcoord-inbox: no watch lock ({lock.path}: {e.strerror or e}); watching without one", file=sys.stderr)
        return lock  # not acquired, holds nothing; release() is a no-op
    pid, started = lock.holder or (_UNKNOWN, _UNKNOWN)
    print(ALREADY_RUNNING.format(pid=pid, started=started), flush=True)
    return None

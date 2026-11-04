"""tools/fabric/control/busy.py — the account's busy locks, across processes.

WHAT IT PROTECTS. upgrade, secrets-sync (with restart) and restart each stop the
account's session and write restart.json. Each module keeps a flag for "one at a time",
but a flag is per process, and an account has two: agentd and `fabric-op` (ADR-029
rule 19, the break-glass path). Two copies of one action, or two different ones, would
both write the marker and both stop the session.

THREE FILES in the account's state directory, each a flock(2) lock:
  busy-marker   the restart marker's owner: an upgrade holds it EXCLUSIVE, a restart
                or a secrets-sync's restart phase holds it SHARED (those two already
                refuse each other by their own locks, and may overlap in count)
  busy-restart  a restart, EXCLUSIVE
  busy-sync     a secrets-sync, EXCLUSIVE (the whole action, as the in-process lock was)
A test-and-set is one kernel call, so two processes starting together cannot both pass.
Where one action must see another's lock it does not hold, `held()` asks with an exclusive
non-blocking lock it drops at once (a shared ask would not see a shared holder); the Dekker order (take yours, then ask theirs) means
two that start together both refuse and never both proceed.

THE PROBE IS A BRIEF HOLDER. `held()` takes its exclusive lock for microseconds, and a `hold()` of
that name landing inside the window would read it as a real holder and refuse with a note naming
an action that is not running (a restart's probe of busy-sync against a sync starting, and the
mirror). So `hold()` retries a few times, PROBE_RETRY_S apart, before it answers "held": the
probe is gone by the first retry, a real holder costs the caller a few milliseconds more. The
probe never makes both proceed; the retry only stops it making one refuse for nothing.

NO STALE OWNER. flock locks belong to the open file description and the kernel drops
them when the holder dies, however it dies; the file's content is never read. The
descriptor is close-on-exec: a child the action starts (the installer, fabric-lease)
must not keep the lock after the daemon is gone.

UNKNOWN STAYS UNKNOWN. A lock file that cannot be opened (state directory unwritable,
a path in the way) raises `Unavailable`; the action reports a failure and stops
nothing. It never reads "cannot lock" as "nobody holds it".
"""
from __future__ import annotations

import fcntl
import os
import time
from typing import Callable

NAMES = ("marker", "restart", "sync")
PROBE_RETRIES = 3
PROBE_RETRY_S = 0.005


class Unavailable(Exception):
    """The lock cannot be taken or asked; the message is one line for the reply."""


def _open(directory: str, name: str) -> int:
    assert name in NAMES
    path = os.path.join(directory, f"busy-{name}")
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        return os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    except OSError as e:
        raise Unavailable(f"cannot open {path}: {e.strerror or e}") from e


def _flock(fd: int, how: int) -> bool:
    try:
        fcntl.flock(fd, how | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    except OSError as e:   # EBADF, ENOLCK, EINTR...: not "held", not "free"
        raise Unavailable(f"flock: {e.strerror or e}") from e
    return True


def hold(directory: str, name: str, *, shared: bool = False,
         sleep: Callable[[float], None] = time.sleep) -> int | None:
    """The descriptor that keeps the lock (release() it), or None when another holder has it
    (still there after PROBE_RETRIES waits: a `held()` probe is not a holder)."""
    fd = _open(directory, name)
    try:
        for attempt in range(PROBE_RETRIES + 1):
            if attempt:
                sleep(PROBE_RETRY_S)
            if _flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX):
                return fd
    except BaseException:
        os.close(fd)
        raise
    os.close(fd)
    return None


def release(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)   # closing the description drops the flock


def held(directory: str, name: str) -> bool:
    """True when anyone holds `name`, shared or exclusive: asked with an exclusive lock dropped at once."""
    fd = _open(directory, name)
    try:
        return not _flock(fd, fcntl.LOCK_EX)
    finally:
        os.close(fd)

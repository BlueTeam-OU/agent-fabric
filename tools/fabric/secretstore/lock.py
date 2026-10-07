"""tools/fabric/secretstore/lock.py — one writer at a time per store.
A part of secret_store.py, which re-exports it; its docstring is the contract.

WHAT IT PROTECTS: a store's working tree, index and HEAD through a whole
write — fetch, verify, rebase, write the entry, commit, push. Two writers
in one store (the agent's own set beside its control agent's self-test, a
parent's two provisioning runs on one child's mirror) interleaved those
steps: one rebased under the other's staged entry, or committed the
other's half-written file (review of the own-secrets PR, R2).

HOW: flock(2) on <store>/.git/agent-fabric-write.lock, waited for up to
WRITE_LOCK_WAIT_S (or less, AGENT_FABRIC_STORE_LOCK_WAIT_S), then a
refusal that names the holder's pid. The kernel
releases a flock when its holder dies, so there is no stale owner to find
or break. The descriptor is close-on-exec: a gpg-agent or git daemon a
write starts must not inherit it and hold the store after the writer is
gone. Re-entrant within a process (assign brings its store up to date,
then sets an entry in it), counted per store path.

The rule is executable: _before_write and _commit refuse a store whose
lock this process does not hold (require_write_lock), so a new writer that
forgets the lock fails its first test instead of racing in production."""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import time

from .core import StoreError

WRITE_LOCK_WAIT_S = 120
# A caller that is itself bounded (the self-test's steps) shortens the wait
# below its own bound, so that it hears the refusal naming the holder, not
# its own timeout. Only shortens: a longer value is the default.
LOCK_WAIT_ENV = "AGENT_FABRIC_STORE_LOCK_WAIT_S"
_POLL_S = 0.1
LOCK_NAME = "agent-fabric-write.lock"
# realpath of a store -> [descriptor or None, depth]
_held: dict[str, list] = {}


def lock_wait_s() -> int:
    raw = os.environ.get(LOCK_WAIT_ENV)
    if raw is None:
        return WRITE_LOCK_WAIT_S
    if not (raw.isascii() and raw.isdigit()) or int(raw) < 1:
        raise StoreError(f"{LOCK_WAIT_ENV}={raw!r} is not a whole number of seconds; nothing written")
    return min(int(raw), WRITE_LOCK_WAIT_S)


def _key(store: str) -> str:
    return os.path.realpath(store)


@contextlib.contextmanager
def write_lock(store: str):
    key = _key(store)
    if key in _held:
        _held[key][1] += 1
        try:
            yield
        finally:
            _held[key][1] -= 1
        return
    git_dir = os.path.join(store, ".git")
    if not os.path.isdir(git_dir):
        # Nothing to lock yet (init locks only after it has made .git):
        # any write here fails on its own first git call, as it did before
        # there was a lock.
        _held[key] = [None, 1]
        try:
            yield
        finally:
            del _held[key]
        return
    path = os.path.join(git_dir, LOCK_NAME)
    wait = lock_wait_s()
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except OSError as e:
        raise StoreError(f"{path}: the store's write lock cannot be opened ({e.strerror}); nothing written") from None
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise StoreError(f"{path}: the store's write lock failed ({e.strerror}); nothing written") from None
                if time.monotonic() >= deadline:
                    raise StoreError(f"another write to {store} has held its lock for {wait} s "
                                     f"(pid {_holder(fd)}, {path}); nothing written — retry when it is done") from None
                time.sleep(_POLL_S)
        # The holder's pid, for the message a waiter gives up with; the
        # lock is the flock, never this text.
        os.ftruncate(fd, 0)
        os.pwrite(fd, f"{os.getpid()}\n".encode(), 0)
    except BaseException:
        os.close(fd)
        raise
    _held[key] = [fd, 1]
    try:
        yield
    finally:
        _held[key][1] -= 1
        if _held[key][1] == 0:
            del _held[key]
            os.close(fd)   # closing the descriptor releases the flock


def _holder(fd: int) -> str:
    try:
        return os.pread(fd, 32, 0).decode(errors="replace").strip() or "?"
    except OSError:
        return "?"


def require_write_lock(store: str) -> None:
    if _key(store) not in _held:
        raise StoreError(f"internal: a write to {store} outside its write lock (secretstore/lock.py); nothing written")

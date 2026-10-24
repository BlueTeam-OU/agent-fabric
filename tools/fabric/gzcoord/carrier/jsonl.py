"""tools/fabric/gzcoord/carrier/jsonl.py — the two things every JSON-lines file
of the carrier needs and a bare os.write gets wrong.

A write can be short (a full disk) and a crash can leave a line without its
newline. Without repair, the next append lands on the torn bytes and the two
merge into one damaged line, which the next restart drops as "torn": an event
that was fsync'd and acted on vanishes (found in review of the first head).
`repair` cuts a torn tail before anything is appended; `append` writes all of a
line or raises, and syncs it."""
from __future__ import annotations

import json
import os


def repair(path: str) -> int:
    """Cut a last line that has no newline; the number of bytes removed."""
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return 0
    try:
        size = os.fstat(fd).st_size
        if size == 0 or os.pread(fd, 1, size - 1) == b"\n":
            return 0
        keep, end = 0, size
        while end > 0:                      # the last newline, searched backwards in chunks
            start = max(end - 65536, 0)
            at = os.pread(fd, end - start, start).rfind(b"\n")
            if at >= 0:
                keep = start + at + 1
                break
            end = start
        os.ftruncate(fd, keep)
        os.fsync(fd)
        return size - keep
    finally:
        os.close(fd)


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            raise OSError("short write")
        view = view[n:]


def append(fd: int, obj: dict) -> None:
    write_all(fd, (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    os.fsync(fd)


def append_path(path: str, obj: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        append(fd, obj)
    finally:
        os.close(fd)

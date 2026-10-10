"""The record of calls (ADR-049 rule 7): time, tool, hit count, the ids returned and whether a read followed a find; never the query's text."""
from __future__ import annotations

import datetime
import json
import os
import sys

LOG = "memory-calls.jsonl"


def append_line(state_dir: str, filename: str, row: dict) -> str | None:
    """One JSON line appended to a private file of the login's state; None, or why it could not be."""
    line = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
    try:
        os.makedirs(state_dir, exist_ok=True)
        fd = os.open(os.path.join(state_dir, filename), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except OSError as e:
        return e.strerror or str(e)
    return None


def now(clock=lambda: datetime.datetime.now(datetime.UTC)) -> str:
    return clock().isoformat(timespec="seconds").replace("+00:00", "Z")


def record(state_dir: str, tool: str, ids: list[str], after_find: bool | None = None) -> None:
    """The log is for counting: a failure to write it is said once on stderr and never fails the call."""
    row: dict = {"t": now(), "tool": tool, "hits": len(ids), "ids": ids}
    if after_find is not None:
        row["after_find"] = after_find       # a read of an id the last find returned: what the read-through rate needs
    failed = append_line(state_dir, LOG, row)
    if failed:
        print(f"fabric-memory: call not counted: {failed}", file=sys.stderr)

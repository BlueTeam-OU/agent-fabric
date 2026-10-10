"""The record of calls (ADR-049 rule 7): time, tool, hit count, the ids returned and whether a read followed a find; never the query's text."""
from __future__ import annotations

import datetime
import json
import os
import sys

LOG = "memory-calls.jsonl"


def record(state_dir: str, tool: str, ids: list[str], after_find: bool | None = None, clock=lambda: datetime.datetime.now(datetime.UTC)) -> None:
    """One line appended. The log is for counting: a failure to write it is said once on stderr and never fails the call."""
    row: dict = {"t": clock().isoformat(timespec="seconds").replace("+00:00", "Z"), "tool": tool, "hits": len(ids), "ids": ids}
    if after_find is not None:
        row["after_find"] = after_find       # a read of an id the last find returned: what the zero-hit and read-through rates need
    line = json.dumps(row, separators=(",", ":")) + "\n"
    try:
        os.makedirs(state_dir, exist_ok=True)
        fd = os.open(os.path.join(state_dir, LOG), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except OSError as e:
        print(f"fabric-memory: call not counted: {e.strerror or e}", file=sys.stderr)

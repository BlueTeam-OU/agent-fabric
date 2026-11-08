"""The record of calls (ADR-049 rule 7): time, tool, hit count, the ids returned and whether a read followed a find; never the query's text."""
from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "runtime"))
import identity  # noqa: E402

LOG = "memory-calls.jsonl"


def append_line(state_dir: str, filename: str, row: dict) -> str | None:
    """One JSON line appended to a private file of the login's state; None, or why it could not be."""
    try:
        identity.append_line(os.path.join(state_dir, filename), json.dumps(row, separators=(",", ":"), ensure_ascii=False))
    except OSError as e:
        return e.strerror or str(e)
    return None


def now(clock=lambda: datetime.datetime.now(datetime.UTC)) -> str:
    return clock().isoformat(timespec="milliseconds").replace("+00:00", "Z")      # not whole seconds: a watermark at one must not drop a row of the same second


def record(state_dir: str, tool: str, ids: list[str], after_find: bool | None = None, project: str | None = None,
           error: bool = False) -> None:
    """The log is for counting: a failure to write it is said once on stderr and never fails the call."""
    row: dict = {"t": now(), "tool": tool, "hits": len(ids), "ids": ids}
    if project:
        row["project"] = project         # the harvest of one project carries the rows of that project alone
    if error:
        row["error"] = True              # a call the caller got wrong: counted apart, never as a zero-hit find
    if after_find is not None:
        row["after_find"] = after_find       # a read of an id the last find returned: what the read-through rate needs
    failed = append_line(state_dir, LOG, row)
    if failed:
        print(f"fabric-memory: call not counted: {failed}", file=sys.stderr)

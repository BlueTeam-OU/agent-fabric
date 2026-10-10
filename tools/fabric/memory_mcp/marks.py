"""A session's verdicts on sections (ADR-049 follow-up): agents/<login>/memory-marks.jsonl, one line each: time, id,
verdict, note. The login's own state; the corpus is never written. A later drain carries stale and wrong marks to the
section's owning role."""
from __future__ import annotations

from memory_mcp import calls

LOG = "memory-marks.jsonl"


def record(state_dir: str, ident: str, verdict: str, note: str) -> str | None:
    return calls.append_line(state_dir, LOG, {"t": calls.now(), "id": ident, "verdict": verdict, "note": note})

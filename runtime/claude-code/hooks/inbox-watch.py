"""What a GZCoord inbox watch looks like in the process table: the one
predicate session-start.py (which says a session has none) and
watch-on-stop.py (which blocks the end of a turn without one) both ask, so
the two cannot disagree on what counts. Loaded by path from the hooks
beside it (as context-sample.py loads session-state.py); no side effects."""
from __future__ import annotations


def is_watch(cmd: str) -> bool:
    """A `gzcoord-inbox` run that waits for a delivery: --until-delivery, --follow
    (a session not yet moved off it) or --wait. `inbox.mjs` is the Node shim
    some callers outside this repository still run; missing either name told
    an armed session to arm a second consumer (review of #42)."""
    return (("gzcoord-inbox" in cmd or "inbox.mjs" in cmd)
            and any(flag in cmd for flag in ("--until-delivery", "--follow", "--wait")))

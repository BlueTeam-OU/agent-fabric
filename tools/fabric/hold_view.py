"""tools/fabric/hold_view.py — how the fleet hold (agent-fabric ADR-037 rule 13)
is read by the job tool, fabric-fresh, fabric-status and the `jobs` op.

The state is `hold.json`, written and read only by runtime/identity.py
(read_hold). This module adds what every reader needs on top: a hold that
cannot be read is a hold (identity.read_hold raises SystemExit for it, and
a corrupt file is somebody's stop that must not become a way through), and
one wording of the hold for the refusal, the status row and the ctl table.

CONTRACT
  read(identity, agent=None)   a record: the hold's own dict, or
                               {"unreadable": <why>} when hold.json cannot
                               be read; None when the login is not held.
                               Never raises for the file's content.
  words(record, now=None)      one line: "<reason> (decision <id>, set by
                               <address>, <age> ago)", or "hold unreadable:
                               <why>". Fields the record lacks are left out.
"""
from __future__ import annotations

import datetime


def read(identity, agent: str | None = None) -> dict | None:
    try:
        return identity.read_hold(agent)
    except SystemExit as exc:
        # SystemExit(str) carries its message; anything else (a code) has none to give.
        return {"unreadable": str(exc.code) if isinstance(exc.code, str) else "hold.json cannot be read"}


def _age(set_at, now: datetime.datetime) -> str | None:
    try:
        then = datetime.datetime.fromisoformat(set_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if then.tzinfo is None:
        return None
    s = max(0, int((now - then).total_seconds()))
    return f"{s} s" if s < 120 else f"{s // 60} min" if s < 7200 else f"{s // 3600} h" if s < 172800 else f"{s // 86400} days"


def words(record: dict, now: datetime.datetime | None = None) -> str:
    if "unreadable" in record:
        return f"hold unreadable: {record['unreadable']}"
    now = now or datetime.datetime.now(datetime.UTC)
    parts = []
    if isinstance(record.get("decision"), str):
        parts.append(f"decision {record['decision']}")
    if isinstance(record.get("set_by"), str):
        parts.append(f"set by {record['set_by']}")
    age = _age(record.get("set_at"), now)
    if age:
        parts.append(f"{age} ago")
    return f"{record['reason']}" + (f" ({', '.join(parts)})" if parts else "")

"""tools/fabric/gzcoord/carrier/position.py — an account's GZCoord read position and delivery health read from the
carrier alone, with no relay cursor (the transport cutover plan's row W13; agent-fabric ADR-067).

The relay keeps one cursor per consumer and `drift.inbox` reads how far behind it is. An account in `carrier-only` has no
such cursor to lag: its position is the spool's unseen count (what arrived and the shown ledger has not settled) and its
health the outbox's outstanding deliveries, the oldest of them and the blocked ones. Both are the carrier's own `unseen`
and `status` ops, read here and nothing moved: neither op acknowledges or settles anything.

CONTRACT
  section(call, runtime_dir, now)
      {"status": "ok", "source": "interweave", "unread", "capped": False, "oldest_unread_at", "lag_s", "lagging",
       "outstanding", "oldest_outstanding_at", "oldest_outstanding_s", "blocked": {code: count}, "awaiting_receipt"}
      with `unread`, `lag_s` and `lagging` the fields the relay's reader answers under, so one renderer reads both. `lag_s`
      is the oldest unseen arrival's age, `lagging` its being over LAG_S (the relay reader's day); an arrival whose stamp
      cannot be read leaves both null, never 0. A carrier that cannot be asked is {"status": "unknown", "reason"}: in
      `carrier-only` the carrier is the only source, so there is nothing to fall back to and nothing is guessed.
  for_mode(mode_state_dir, ...)
      None unless the account is in `carrier-only`; then `section`. A mode that cannot be read is
      {"status": "unknown", "reason"}: an unreadable file must not quietly send the read to the relay either.
  The relay is never called from here."""
from __future__ import annotations

import datetime
import os
import time
from typing import Any, Callable

from ..transport import mode as _mode
from . import server

# One day, as drift.LAG_S (a test holds them equal): what "behind" means must not differ with the transport that is read.
LAG_S = 86400
TIMEOUT_S = 5.0
# fabric-status asks once, in every session start: a hung carrier must not cost it the full read bound.
JOURNAL_TIMEOUT_S = 2.0
# A delivery still outstanding after this long is "stranded" for the soak of gate 2 (cutover plan D8): the outbox retries from 1 s
# doubling to 5 min, so ten minutes is two attempts at the ceiling past a receipt that should take seconds.
STRANDED_AFTER_S = 600


def _age(stamp: Any, now: float) -> int | None:
    if not isinstance(stamp, str):
        return None
    try:
        then = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        return None
    return max(0, int(now - then.timestamp()))


def _oldest(stamps: list[Any], now: float) -> tuple[Any, int | None]:
    """The oldest stamp and its age. One stamp that cannot be read makes the age unknown: the oldest might be that one."""
    ages = [_age(s, now) for s in stamps]
    if not stamps or None in ages:
        return None, None
    oldest = max(range(len(ages)), key=ages.__getitem__)
    return stamps[oldest], ages[oldest]


def section(call: Callable[..., dict] = server.call, runtime_dir: str | None = None, now: float | None = None) -> dict:
    rd = os.environ.get("XDG_RUNTIME_DIR") if runtime_dir is None else runtime_dir
    if not rd or not os.path.isabs(rd):
        return {"status": "unknown", "reason": "XDG_RUNTIME_DIR is not set: the carrier's socket cannot be found"}
    sock = server.socket_path(rd)
    now = time.time() if now is None else now
    try:
        unseen = call(sock, {"op": "unseen"}, timeout=TIMEOUT_S)
        status = call(sock, {"op": "status"}, timeout=TIMEOUT_S)
    except OSError as e:
        return {"status": "unknown", "reason": f"the InterWeave carrier did not answer ({e.__class__.__name__}: {e})"}
    for op, out in (("unseen", unseen), ("status", status)):
        if not isinstance(out, dict) or not out.get("ok"):
            why = out.get("error", "no reason given") if isinstance(out, dict) else "not an object"
            return {"status": "unknown", "reason": f"the InterWeave carrier refused {op} ({why})"}
    records, pending = unseen.get("records"), status.get("outstanding")
    if not isinstance(records, list) or not isinstance(pending, list):
        return {"status": "unknown", "reason": "the InterWeave carrier's answer is not the contract's lists"}
    at, lag = _oldest([r.get("ts") if isinstance(r, dict) else None for r in records], now)
    out_at, out_s = _oldest([d.get("queued_at") if isinstance(d, dict) else None for d in pending], now)
    blocked: dict[str, int] = {}
    for d in pending:
        if isinstance(d, dict) and d.get("blocked"):
            blocked[str(d["blocked"])] = blocked.get(str(d["blocked"]), 0) + 1
    return {"status": "ok", "source": "interweave", "unread": len(records), "capped": False,
            "oldest_unread_at": at, "lag_s": lag if records else 0,
            "lagging": (lag > LAG_S if lag is not None else None) if records else False,
            "outstanding": len(pending), "oldest_outstanding_at": out_at, "oldest_outstanding_s": out_s,
            "blocked": blocked,
            "awaiting_receipt": sum(1 for d in pending if isinstance(d, dict) and d.get("posted"))}


def journal_refusals(call: Callable[..., dict] = server.call, runtime_dir: str | None = None) -> dict:
    """What the carrier's status op says of arrivals its journal refused since it started (engine.Counters.not_journaled), for
    fabric-status: {"status": "none"} where no carrier socket exists (nothing to say, never printed); {"status": "unknown",
    "reason"} where one exists and cannot be read; else {"status": "ok", "not_journaled": n, "last": {mid, at, error} | None},
    `last` None when the count is nonzero and the running carrier does not report it (one older than the field). A carrier
    that was restarted counts from zero: the number is "since it started", and says so where it is printed."""
    rd = os.environ.get("XDG_RUNTIME_DIR") if runtime_dir is None else runtime_dir
    if not rd or not os.path.isabs(rd):
        return {"status": "none"}
    sock = server.socket_path(rd)
    if not os.path.exists(sock):
        return {"status": "none"}
    try:
        status = call(sock, {"op": "status"}, timeout=JOURNAL_TIMEOUT_S)
    except OSError as e:
        return {"status": "unknown", "reason": f"the InterWeave carrier did not answer ({e.__class__.__name__}: {e})"}
    counters = status.get("counters") if isinstance(status, dict) and status.get("ok") else None
    n = counters.get("not_journaled") if isinstance(counters, dict) else None
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        return {"status": "unknown", "reason": "the InterWeave carrier's status has no not_journaled count"}
    last = status.get("not_journaled_last")
    ok = isinstance(last, dict) and all(isinstance(last.get(k), str) for k in ("mid", "at", "error"))
    return {"status": "ok", "not_journaled": n, "last": {k: last[k] for k in ("mid", "at", "error")} if ok else None}


def for_mode(mode_state_dir: str | None = None, **opts: Any) -> dict | None:
    try:
        m = _mode.read(mode_state_dir)["mode"]
    except _mode.ModeError as e:
        return {"status": "unknown", "reason": str(e)}
    return section(**opts) if m == _mode.CARRIER_ONLY else None


def stranded(call: Callable[..., dict] = server.call, runtime_dir: str | None = None, now: float | None = None,
             older_than_s: int = STRANDED_AFTER_S) -> dict:
    """The outbox alone, in any transport mode (`section` is for carrier-only and reads the spool too): how many deliveries are
    outstanding, how many are older than `older_than_s`, the oldest one's age, and the blocked ones, metadata only (no mid, no
    recipient, no text). A queued_at that cannot be read is counted as stranded and leaves the age null: unknown is not young.
    {"status": "unknown", "reason"} when the carrier cannot be asked; the relay is never called."""
    rd = os.environ.get("XDG_RUNTIME_DIR") if runtime_dir is None else runtime_dir
    if not rd or not os.path.isabs(rd):
        return {"status": "unknown", "reason": "XDG_RUNTIME_DIR is not set: the carrier's socket cannot be found"}
    now = time.time() if now is None else now
    try:
        status = call(server.socket_path(rd), {"op": "status"}, timeout=TIMEOUT_S)
    except OSError as e:
        return {"status": "unknown", "reason": f"the InterWeave carrier did not answer ({e.__class__.__name__}: {e})"}
    if not isinstance(status, dict) or not status.get("ok"):
        why = status.get("error", "no reason given") if isinstance(status, dict) else "not an object"
        return {"status": "unknown", "reason": f"the InterWeave carrier refused status ({why})"}
    pending = status.get("outstanding")
    if not isinstance(pending, list):
        return {"status": "unknown", "reason": "the InterWeave carrier's answer is not the contract's list"}
    ages = [_age(d.get("queued_at") if isinstance(d, dict) else None, now) for d in pending]
    blocked: dict[str, int] = {}
    for d in pending:
        if isinstance(d, dict) and d.get("blocked"):
            blocked[str(d["blocked"])] = blocked.get(str(d["blocked"]), 0) + 1
    known = [a for a in ages if a is not None]
    return {"status": "ok", "outstanding": len(pending), "older_than_s": older_than_s,
            "older": sum(1 for a in ages if a is None or a > older_than_s),
            "oldest_s": None if None in ages else max(known, default=0), "blocked": blocked}

"""tools/fabric/gzcoord/carrier/adapter.py — what the send and inbox adapters
use to reach the carrier (CARRIER-CONTRACT.md §6), and the arrival log the
inbox keeps beside its journal (ADR-064 rule 11).

THE SWITCH. ADR-064 builds the carrier behind a switch that is off by
default. The switch is the carrier itself: with no carrier process there is
no socket, `present()` is False and every call here is a no-op that costs a
stat. Nothing is configured per tool, and a session that has no carrier is a
session of the relay alone, as before.

THE RELAY FAILS OPEN. A carrier that is present and does not answer must never
hold a relay delivery: `claim` answers "first" (show it) and `unseen` answers
nothing when the carrier cannot be asked, and the send side reports what
happened and carries on. The relay stays the transport of record (rule 11).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Callable

from . import arrivals, jsonl, server

CLAIM_TIMEOUT = 2.0
SEND_TIMEOUT = 12.0


# After a carrier that is there did not answer, nothing is asked of it for this
# long: each relay record makes a claim, and a hung carrier must not cost the
# relay's delivery two seconds a record.
DOWN_FOR = 30.0


class Adapter:
    """`pending`, a path in the account's state, is where a relay show the carrier
    could not be told of is kept until it can be: a relay copy shown under fail-open
    would otherwise be shown again when the carrier's copy of the message is
    offered (review of the first head, F7)."""

    def __init__(self, path: str | None = None, call: Callable[..., dict] = server.call, pending: str | None = None,
                 spool: str | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        if path is None:
            rd = os.environ.get("XDG_RUNTIME_DIR")
            path = server.socket_path(rd) if rd and os.path.isabs(rd) else ""
        self.path, self._call, self._pending, self._spool, self._clock = path, call, pending, spool, clock
        self._down_until = 0.0

    def present(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    def _ask(self, req: dict, timeout: float, flush: bool = True) -> dict | None:
        if not self.present() or self._clock() < self._down_until:
            return None
        if flush and not self._flush_pending():
            return None
        try:
            out = self._call(self.path, req, timeout=timeout)
        except OSError as e:
            self._down_until = self._clock() + DOWN_FOR
            print(f"gzcoord: the InterWeave carrier did not answer ({e}); the relay carries on", file=sys.stderr)
            return None
        if not out.get("ok"):
            print(f"gzcoord: the InterWeave carrier refused ({out.get('error', 'no reason given')}); the relay carries on",
                  file=sys.stderr)
            return None
        return out

    def post(self, mid: str, text: str) -> str:
        """accepted (durably queued for every recipient it carries), not-carried
        (no roster recipient: relay alone), absent (no carrier) or failed."""
        if not self.present():
            return "absent"
        out = self._ask({"op": "send", "message_id": mid, "text": text}, SEND_TIMEOUT)
        if out is None:
            return "failed"
        if out.get("carried", 0) == 0:
            return "not-carried"
        return "accepted" if out.get("queued") == out.get("carried") else "failed"

    def claim(self, mid: str, via: str) -> dict:
        out = self._ask({"op": "claim", "message_id": mid, "via": via}, CLAIM_TIMEOUT)
        if out is None:
            # Noted when a carrier is there, or has left arrivals behind (it crashed):
            # its restart offers those, and the relay's show must reach it first.
            if via == "relay" and self._pending and (self.present() or self._has_spool()):
                self._keep_pending(mid)
            return {"first": True, "shown_via": None, "reshow": False}
        return out

    def _has_spool(self) -> bool:
        try:
            return bool(self._spool) and os.path.getsize(self._spool) > 0
        except OSError:
            return False

    def _keep_pending(self, mid: str) -> None:
        try:
            jsonl.repair(self._pending)
            jsonl.append_path(self._pending, {"mid": mid})
        except OSError as e:
            print(f"gzcoord: a relay show could not be noted for the carrier ({e.strerror or e}); "
                  "the message may be offered again", file=sys.stderr)

    def _flush_pending(self) -> bool:
        """Tell the carrier of the relay shows it missed. False when it could not
        be told (it is then asked nothing else this time)."""
        if not self._pending or not os.path.exists(self._pending):
            return True
        try:
            with open(self._pending, encoding="utf-8") as fh:
                mids = [json.loads(line)["mid"] for line in fh if line.strip()]
        except (OSError, ValueError, KeyError):
            return True
        for mid in mids:
            try:
                out = self._call(self.path, {"op": "claim", "message_id": mid, "via": "relay"}, timeout=CLAIM_TIMEOUT)
            except OSError:
                self._down_until = self._clock() + DOWN_FOR
                return False
            if not out.get("ok"):
                return False
        try:
            os.unlink(self._pending)
        except OSError:
            pass
        return True

    def unseen(self) -> list[dict]:
        out = self._ask({"op": "unseen"}, CLAIM_TIMEOUT)
        return list(out.get("records", [])) if out else []


def relay_arrivals(log: arrivals.ArrivalLog, address: str, mids: list[str]) -> None:
    """One line per relay copy addressed here, before the journal collapses it.
    The relay authenticates nobody (ADR-033 §6), so its verdict is
    `unauthenticated`, never `ok`. A page the journal holds is read again every
    retry; that re-read of an unacknowledged record is not a copy received, so a
    message is logged once per process (a relay that delivers it twice to one
    running watch is the relay's duplicate suppression's, not ours)."""
    for mid in mids:
        if mid in _logged_here:
            continue
        _logged_here.add(mid)
        log.append(mid, address, "relay", "unauthenticated")


_logged_here: set[str] = set()

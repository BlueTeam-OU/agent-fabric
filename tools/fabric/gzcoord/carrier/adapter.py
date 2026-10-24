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

import os
import sys
from typing import Callable

from . import arrivals, server

CLAIM_TIMEOUT = 2.0
SEND_TIMEOUT = 12.0


class Adapter:
    def __init__(self, path: str | None = None, call: Callable[..., dict] = server.call) -> None:
        if path is None:
            rd = os.environ.get("XDG_RUNTIME_DIR")
            path = server.socket_path(rd) if rd and os.path.isabs(rd) else ""
        self.path, self._call = path, call

    def present(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    def _ask(self, req: dict, timeout: float) -> dict | None:
        if not self.present():
            return None
        try:
            out = self._call(self.path, req, timeout=timeout)
        except OSError as e:
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
            return {"first": True, "shown_via": None, "reshow": False}
        return out

    def unseen(self) -> list[dict]:
        out = self._ask({"op": "unseen"}, CLAIM_TIMEOUT)
        return list(out.get("records", [])) if out else []


def relay_arrivals(log: arrivals.ArrivalLog, address: str, mids: list[str]) -> None:
    """One line per relay copy addressed here, before the journal collapses it.
    The relay authenticates nobody (ADR-033 §6), so its verdict is
    `unauthenticated`, never `ok`."""
    for mid in mids:
        log.append(mid, address, "relay", "unauthenticated")

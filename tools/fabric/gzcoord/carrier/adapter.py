"""tools/fabric/gzcoord/carrier/adapter.py — what the send and inbox adapters
use to reach the carrier (CARRIER-CONTRACT.md §6), and the arrival log the
inbox keeps beside its journal (ADR-064 rule 11).

THE SWITCH. ADR-064 builds the carrier behind a switch that is off by default.
The switch is the carrier itself: with no carrier process there is no socket,
`present()` is False and every call here is a no-op that costs a stat. Nothing
is configured per tool, and a session that has no carrier is a session of the
relay alone, as before.

THE RELAY FAILS OPEN. A carrier that is present and does not answer must never
hold a relay delivery: `unseen` answers nothing when the carrier cannot be
asked, and the send side reports what happened and carries on. What a session
sees is decided by the shown ledger (ledger.py), which the inbox reaches on its
own; the relay stays the transport of record (rule 11).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Callable

from . import arrivals, framing, server

CLAIM_TIMEOUT = 2.0
SEND_TIMEOUT = 12.0
# After a carrier that is there did not answer, nothing is asked of it for this
# long: the inbox asks once a pass, and a hung carrier must not cost the relay's
# delivery two seconds a pass.
DOWN_FOR = 30.0


class Adapter:
    def __init__(self, path: str | None = None, call: Callable[..., dict] = server.call,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if path is None:
            rd = os.environ.get("XDG_RUNTIME_DIR")
            path = server.socket_path(rd) if rd and os.path.isabs(rd) else ""
        self.path, self._call, self._clock = path, call, clock
        self._down_until = 0.0

    def present(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    def _ask(self, req: dict, timeout: float) -> dict | None:
        if not self.present() or self._clock() < self._down_until:
            return None
        try:
            out = self._call(self.path, req, timeout=timeout)
        except OSError as e:
            self._down_until = self._clock() + DOWN_FOR
            print(f"gzcoord: the InterWeave carrier did not answer ({e}); the relay carries on", file=sys.stderr)
            return None
        if not out.get("ok"):
            queued = f", {out['queued']} recipient(s) recorded" if "queued" in out else ""
            print(f"gzcoord: the InterWeave carrier refused ({out.get('error', 'no reason given')}{queued}); "
                  "the relay carries on", file=sys.stderr)
            return None
        return out

    def post(self, mid: str, text: str) -> str:
        """accepted (every recipient durably recorded), not-carried (no roster
        recipient: relay alone), absent (no carrier) or failed. The request is
        encoded first and refused here, naming its size, when the message is over
        the 4 MiB the carrier carries or the line over the 9 MiB it reads."""
        if not self.present():
            return "absent"
        line = json.dumps({"op": "send", "message_id": mid, "text": text}, separators=(",", ":"), ensure_ascii=False)
        size, body = len(line.encode("utf-8")), len(text.encode("utf-8"))
        if body > framing.MAX_TEXT or size > server.MAX_REQUEST:
            print(f"gzcoord: the message is {body} bytes, its request {size}: over the {framing.MAX_TEXT >> 20} MiB "
                  f"the carrier carries or the {server.MAX_REQUEST >> 20} MiB it reads; the relay carries it",
                  file=sys.stderr)
            return "failed"
        out = self._ask({"op": "send", "message_id": mid, "text": text}, SEND_TIMEOUT)
        if out is None:
            return "failed"
        if out.get("carried", 0) == 0:
            return "not-carried"
        return "accepted" if out.get("queued") == out.get("carried") else "failed"

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

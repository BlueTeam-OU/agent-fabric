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
import threading
import time
from dataclasses import dataclass
from typing import Callable

from . import arrivals, framing, server

CLAIM_TIMEOUT = 2.0
SEND_TIMEOUT = 12.0
# After a carrier that is there did not answer, nothing is asked of it for this
# long: the inbox asks once a pass, and a hung carrier must not cost the relay's
# delivery two seconds a pass.
DOWN_FOR = 30.0
# The longest one `wait` call is asked to hold; the carrier clamps it too (engine.MAX_WAIT).
WAIT_MAX = 55.0
WAIT_SLACK = 5.0     # what the socket may take beyond the wait asked for


class CarrierError(Exception):
    """The carrier, as the transport of record, did not do what was asked. `never_reached_it` is True only when the failure
    proves the carrier recorded nothing of the request (no carrier, a request refused before any record, nothing queued);
    a call that was sent and not answered may have been recorded, and says False."""

    def __init__(self, message: str, *, absent: bool = False, never_reached_it: bool = False) -> None:
        super().__init__(message)
        self.absent, self.never_reached_it = absent, never_reached_it


@dataclass(frozen=True)
class Post:
    """What `Adapter.post_result` knows of one send: the state `post` answers, and why when it is not accepted."""
    state: str            # accepted | not-carried | absent | failed
    detail: str = ""
    proved_unsent: bool = False   # no recipient was recorded by this call


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
        return self.post_result(mid, text, fail_open=True).state

    def post_result(self, mid: str, text: str, *, fail_open: bool = False) -> Post:
        """`post` with what a primary must say when it is not accepted. `fail_open` keeps the mirror's lines on stderr ("the
        relay carries on"); without it nothing is printed here and the caller owns the words."""
        if not self.present():
            return Post("absent", "no InterWeave carrier is running", proved_unsent=True)
        line = json.dumps({"op": "send", "message_id": mid, "text": text}, separators=(",", ":"), ensure_ascii=False)
        size, body = len(line.encode("utf-8")), len(text.encode("utf-8"))
        if body > framing.MAX_TEXT or size > server.MAX_REQUEST:
            detail = (f"the message is {body} bytes, its request {size}: over the {framing.MAX_TEXT >> 20} MiB "
                      f"the carrier carries or the {server.MAX_REQUEST >> 20} MiB it reads")
            if fail_open:
                print(f"gzcoord: {detail}; the relay carries it", file=sys.stderr)
            return Post("failed", detail, proved_unsent=True)
        req = {"op": "send", "message_id": mid, "text": text}
        if fail_open:
            out = self._ask(req, SEND_TIMEOUT)
            if out is None:
                return Post("failed")
        else:
            try:
                out = self._call(self.path, req, timeout=SEND_TIMEOUT)
            except OSError as e:
                # Sent and not answered, or not sent: the carrier may hold it.
                return Post("failed", f"the InterWeave carrier did not answer ({e})")
            if not out.get("ok"):
                queued = out.get("queued", 0) if "queued" in out else 0
                return Post("failed", str(out.get("error", "no reason given")), proved_unsent=not queued)
        if out.get("carried", 0) == 0:
            return Post("not-carried", "no roster member carries the message's TO", proved_unsent=True)
        return Post("accepted") if out.get("queued") == out.get("carried") else Post("failed", "not every recipient was recorded")

    def unseen(self) -> list[dict]:
        out = self._ask({"op": "unseen"}, CLAIM_TIMEOUT)
        return list(out.get("records", [])) if out else []

    def wait(self, seconds: float, abort: threading.Event | None = None) -> list[dict]:
        """The carrier as the transport of record waits for the watch: the records `unseen` lists, held up to `seconds`
        (at most WAIT_MAX) until there is one. Strict: a carrier that is not there, does not answer or refuses raises
        CarrierError, never an empty answer, for an empty list is "nothing arrived" and would make a dead carrier an
        idle watch. `abort` is looked at before the call only: the call itself ends at the carrier's own bound."""
        seconds = max(0.0, min(WAIT_MAX, seconds))
        if not self.present():
            raise CarrierError("no InterWeave carrier is running", absent=True, never_reached_it=True)
        if abort is not None and abort.is_set():
            return []
        try:
            out = self._call(self.path, {"op": "wait", "seconds": seconds}, timeout=seconds + WAIT_SLACK)
        except OSError as e:
            raise CarrierError(f"the InterWeave carrier did not answer ({e})") from e
        if not out.get("ok"):
            raise CarrierError(f"the InterWeave carrier refused ({out.get('error', 'no reason given')})")
        return list(out.get("records", []))


def relay_arrivals(log: arrivals.ArrivalLog, address: str, copies: list[tuple[str, str]]) -> None:
    """One line per relay copy addressed here, before the journal collapses it.
    The relay authenticates nobody (ADR-033 §6), so its verdict is
    `unauthenticated`, never `ok`. A page the journal holds is read again every
    retry; that re-read of an unacknowledged record is not a copy received, so a
    relay RECORD (its id, `copies` being (record id, MESSAGE-ID)) is logged once per
    process; a second record of the same message (a retransmission, a redelivery) is
    another copy and another line."""
    for rid, mid in copies:
        if rid in _logged_here:
            continue
        _logged_here.add(rid)
        log.append(mid, address, "relay", "unauthenticated")


_logged_here: set[str] = set()

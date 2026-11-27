"""tools/fabric/gzcoord/transport/mux.py — the one transport as the inbox and the sender use it (agent-fabric ADR-064
rules 6, 7, 11; ADR-067; the transport cutover plan's W15).

THE CARRIER IS THE RECORD. There is no mirror and no second transport: what the primary fails with is what the inbox reports and
the sender exits on. The mux keeps the shape the callers were written against (`send_primary`, `fetch_page`, `unseen`, `iw`,
`ledger`) so the watch loop and the sender do not name a transport.

RECEIVING is the carrier's `receive` (the wait, whose error is raised: a dead carrier is not an idle watch) and its records are
`unseen()`; what is shown is decided by the shown ledger (dedup.py). `fetch_page` answers an empty page: the page shape is the
watch loop's, and nothing but the carrier brings a record. The carrier has nothing to be told when a record is shown (its ledger
settles an arrival), so `ack` is a no-op.

The shown ledger beside the journal belongs to the receiving side; a mux built to send only has none."""
from __future__ import annotations

import os
import threading
from typing import Any, Callable

from ..carrier import ledger
from .base import Health, Primary, Sent


class TransportMux:
    def __init__(self, primary: Primary, *, me: dict | None = None, state_dir: str | None = None,
                 iso_now: Callable[[], str] | None = None) -> None:
        self.primary = primary
        self._carried: list[dict] = []     # what the carrier's wait listed, handed to the watch by `unseen`
        self._me = me or {}
        self.ledger: Any = None
        if state_dir is not None:
            assert iso_now is not None
            self.ledger = ledger.Ledger(os.path.join(state_dir, "gzcoord-shown.jsonl"), iso_now=iso_now)

    def send_primary(self, message_id: str, text: str) -> Sent:
        return self.primary.send(message_id, text)

    def fetch_page(self, seconds: float, abort: threading.Event) -> dict:
        self._carried = self.primary.receive(seconds, abort)
        return {"messages": []}

    def ack(self, record_id: Any) -> None:
        """Nothing to tell the carrier: its ledger settles an arrival."""

    @property
    def iw(self) -> "TransportMux":
        """What wait_loop asks for the carrier's arrivals: this mux."""
        return self

    def unseen(self) -> list[dict]:
        # The wait's own answer, once: asking the carrier again would be a second call a slice, and a record not shown
        # is listed by the next wait.
        carried, self._carried = self._carried, []
        return carried

    def health(self) -> list[Health]:
        """One carrier, one report."""
        return [self.primary.health()]

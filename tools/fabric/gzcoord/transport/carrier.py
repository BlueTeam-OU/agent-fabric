"""tools/fabric/gzcoord/transport/carrier.py — the second carrier as a mirror transport, over carrier/adapter.py
(CARRIER-CONTRACT.md §6). The adapter's switch is the carrier itself: with no carrier running every verb here is a no-op that
costs a stat, and a carrier that does not answer is a line on stderr from the adapter, never an error raised (the relay
fails open, ADR-064)."""
from __future__ import annotations

import threading
from typing import Any

from ..carrier import CARRIER_NAME, adapter
from .base import Health, Sent

NAME = CARRIER_NAME


class CarrierTransport:
    name = NAME

    def __init__(self, ask: adapter.Adapter | None = None) -> None:
        # One adapter for the life of the transport: it remembers that a carrier did not answer, and does not ask again for
        # adapter.DOWN_FOR seconds.
        self._adapter = adapter.Adapter() if ask is None else ask

    def send(self, message_id: str, text: str) -> Sent:
        return Sent(self.name, self._adapter.post(message_id, text))

    def receive(self, seconds: float, abort: threading.Event) -> list[dict]:
        return self._adapter.unseen()

    def ack(self, record_id: Any) -> None:
        """Nothing to tell the carrier: what it journaled is shown or not by the shown ledger, which lists a record again on
        every pass until it holds the final line (carrier/arrivals.py)."""

    def health(self) -> Health:
        return Health(self.name, self._adapter.present())

"""tools/fabric/gzcoord/transport/carrier.py — the second carrier as a mirror transport, over carrier/adapter.py
(CARRIER-CONTRACT.md §6). The adapter's switch is the carrier itself: with no carrier running every verb here is a no-op that
costs a stat, and a carrier that does not answer is a line on stderr from the adapter, never an error raised (the relay
fails open, ADR-064). That is the mirror, CarrierTransport; CarrierPrimary below, the carrier as the record, raises."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .. import i18n, placement
from ..carrier import CARRIER_LABEL, CARRIER_NAME, adapter
from ..gzmsg import en
from .base import Health, Sent

NAME = CARRIER_NAME


def fix_line(t: i18n.Printer, address: str) -> str:
    """The {fix} of every carrier line, by who reads it: fabric-ctl refuses a login that is not a host operator, so an agent
    told to run it could do nothing (2026-11-18, two agents asked the owner). Anyone else is told what they can do."""
    if address and placement.is_operator(address):
        return t("carrier.fix", {"login": address.rpartition("/")[2], "name": CARRIER_NAME})
    return t("carrier.fix-agent", {})


class CarrierTransport:
    name = NAME

    def __init__(self, ask: adapter.Adapter | None = None) -> None:
        # One adapter for the life of the transport: it remembers that a carrier did not answer, and does not ask again for
        # adapter.DOWN_FOR seconds.
        self._adapter = adapter.Adapter() if ask is None else ask

    def send(self, message_id: str, text: str) -> Sent:
        post = self._adapter.post_result(message_id, text, fail_open=True)
        return Sent(self.name, post.state, detail=post.detail)

    def receive(self, seconds: float, abort: threading.Event) -> list[dict]:
        return self._adapter.unseen()

    def ack(self, record_id: Any) -> None:
        """Nothing to tell the carrier: what it journaled is shown or not by the shown ledger, which lists a record again on
        every pass until it holds the final line (carrier/arrivals.py)."""

    def health(self) -> Health:
        return Health(self.name, self._adapter.present())


# What `receive` waits at most between two looks at a record the carrier lists again and again: one the shown ledger has
# not settled (a hold, a journal that cannot keep it) comes back at once on every call, and a watch that took it as news
# would spin.
SAME_PAGE_PAUSE_S = 2.0


class CarrierPrimary(CarrierTransport):
    """The carrier as the transport of record (ADR-064 rule 11, mode carrier-record or carrier-only). What the mirror above
    swallows this one raises: a send the carrier did not accept, a wait it did not answer, are the caller's exit status and
    line, never a quiet "nothing arrived". `receive` is the watch's clock: the adapter's `wait` op holds until a record is
    listed, so an idle arm costs one adapter call per slice."""

    def __init__(self, ask: adapter.Adapter | None = None, *, address: str = "",
                 journal_newest: Callable[[int], list[dict]] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(ask)
        self._address, self._login = address, address.rpartition("/")[2]
        self._journal_newest, self._clock = journal_newest, clock
        self._last_ids: tuple[str, ...] = ()
        self._last_at = 0.0

    def send(self, message_id: str, text: str) -> Sent:
        """accepted, or CarrierError: no recipient on the roster, no carrier, a request too large, or some recipients not
        recorded (those that were stay recorded and are sent). `Sent` carries no seq: the MESSAGE-ID names the message."""
        post = self._adapter.post_result(message_id, text)
        if post.state == "accepted":
            return Sent(self.name, "accepted")
        raise adapter.CarrierError(post.detail or f"the carrier answered {post.state}", absent=post.state == "absent",
                                   never_reached_it=post.proved_unsent)

    def receive(self, seconds: float, abort: threading.Event) -> list[dict]:
        records = self._adapter.wait(seconds, abort)
        ids = tuple(str(r.get("message_id")) for r in records)
        now = self._clock()
        if records and ids == self._last_ids and now - self._last_at < SAME_PAGE_PAUSE_S:
            # Listed again at once: not news. Hold the rest of the pause, ending early for an abort.
            abort.wait(max(0.0, min(seconds, SAME_PAGE_PAUSE_S - (now - self._last_at))))
        self._last_ids, self._last_at = ids, self._clock()
        return records

    def newest(self, limit: int, timeout: float | None = None) -> Any:
        """The journal's newest rows (inbox_parts/records.py `journal_newest`): the carrier keeps no past of its own."""
        if self._journal_newest is None:
            raise adapter.CarrierError("this transport was opened without a journal to read")
        return {"messages": self._journal_newest(limit)}

    def refresh(self, error: BaseException) -> bool:
        return False      # the carrier has no token: the PeerId is the credential (ADR-064 rule 9)

    def explain(self, error: BaseException, t: i18n.Printer | None = None) -> dict:
        """The one line for a failure of the carrier. Code 0: the carrier being down is not a refusal no retry cures."""
        t = t or en()
        fix = fix_line(t, getattr(self, "_address", ""))
        if isinstance(error, adapter.CarrierError) and error.absent:
            return {"line": t("transport.carrier-absent", {"carrier": CARRIER_LABEL, "fix": fix}), "code": 0}
        return {"line": t("transport.carrier-failed", {"carrier": CARRIER_LABEL, "detail": str(error), "fix": fix}), "code": 0}

    def never_delivered(self, error: BaseException) -> bool:
        """Only a carrier that recorded nothing of the send: none running, a request it never read, or no recipient it
        queued. A call that was sent and not answered may have been recorded; the outbox then retries it."""
        return isinstance(error, adapter.CarrierError) and error.never_reached_it

"""tools/fabric/gzcoord/transport/mux.py — the primary transport and its mirrors, as the inbox and the sender use them
(agent-fabric ADR-064 rules 6, 7, 11; ADR-067).

THE PRIMARY IS THE RECORD. What it fails with is what the inbox reports and the sender exits on; a mirror that fails is a line
from its own transport and nothing else. Both are sent every message, the mirrors after the primary's outcome is known,
whatever it was; the sender interleaves its journal rows between the two, so they are two calls.

RECEIVING is the primary's page; the mirrors' records come in the same pass through the shown ledger (dedup.py) and are never
acknowledged to the primary. The acknowledgement waits for the journal and the showing: that order is watch.wait_loop's, which
calls `ack` and holds the ledger's lock, and is not decided here.

The logs beside the journal (arrival and acknowledgement logs, the shown ledger) belong to the receiving side; a mux built to
send only has none."""
from __future__ import annotations

import hashlib
import os
import sys
import threading
from typing import Any, Callable, Sequence

from .. import gzmsg
from ..carrier import adapter, arrivals, ledger
from ..inbox_parts.tokens import for_me
from .base import Health, Primary, Sent, Transport


class TransportMux:
    def __init__(self, primary: Primary, mirrors: Sequence[Transport] = (), *, me: dict | None = None,
                 state_dir: str | None = None, iso_now: Callable[[], str] | None = None) -> None:
        self.primary, self.mirrors = primary, list(mirrors)
        self._me = me or {}
        self._of_record: dict[Any, str] = {}   # primary record id -> MESSAGE-ID, for the acknowledgement log
        self.ledger: Any = None
        self.mode: str = "relay-record"   # open_transport sets it from the account's state; a mux built by hand is the default
        self._arrivals: Any = None
        self._acks: Any = None
        if state_dir is not None:
            assert iso_now is not None
            self._arrivals = arrivals.ArrivalLog(os.path.join(state_dir, "gzcoord-arrivals.jsonl"), iso_now=iso_now)
            self.ledger = ledger.Ledger(os.path.join(state_dir, "gzcoord-shown.jsonl"), iso_now=iso_now)
            self._acks = arrivals.AckLog(os.path.join(state_dir, "gzcoord-acks.jsonl"), iso_now=iso_now)

    # ── sending ──────────────────────────────────────────────────────

    def send_primary(self, message_id: str, text: str) -> Sent:
        return self.primary.send(message_id, text)

    def send_mirrors(self, message_id: str, text: str) -> list[Sent]:
        return [m.send(message_id, text) for m in self.mirrors]

    # ── receiving, in the shape inbox_parts/watch.wait_loop takes ────

    def fetch_page(self, seconds: float, abort: threading.Event) -> dict:
        records = self.primary.receive(seconds, abort)
        self._remember_ids(records)
        return {"messages": records}

    def _remember_ids(self, records: list[dict]) -> None:
        """primary record id -> MESSAGE-ID for the records of a fetched page addressed here: the acknowledgement knows only
        the first, and the relay-outage drill's evidence is by the second. Others' traffic the watch passes through
        acknowledged is no evidence of ours, and a message with no MESSAGE-ID has no id worth keeping (the arrival log's hash
        of its text is not sent anywhere)."""
        for r in records:
            try:
                msg = gzmsg.parse(r["content"])
                if for_me(msg, self._me) and msg["metadata"].get("MESSAGE-ID"):
                    self._of_record[r["id"]] = msg["metadata"]["MESSAGE-ID"]
            except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
                continue      # not GZCOORD/1: never an arrival

    def ack(self, record_id: Any) -> Any:
        try:
            self.primary.ack(record_id)
        except Exception:
            self._log_ack(self._of_record.get(record_id), False)
            raise
        self._log_ack(self._of_record.pop(record_id, None), True)

    def _log_ack(self, mid: Any, ok: bool) -> None:
        if not isinstance(mid, str) or self._acks is None:
            return
        try:
            self._acks.append_ack(mid, self._me["address"], ok)
        except OSError as e:
            # Evidence for the parity report, not a condition of acknowledging.
            print(f"gzcoord: the acknowledgement log could not be written ({e.strerror or e})", file=sys.stderr)

    @property
    def iw(self) -> "TransportMux | None":
        """What wait_loop asks for the mirrors' arrivals: this mux, or None with no mirror (the route is the primary alone)."""
        return self if self.mirrors else None

    def unseen(self) -> list[dict]:
        return [r for m in self.mirrors for r in m.receive(0, threading.Event())]

    def on_arrival(self, recs: list[dict]) -> None:
        """One line per primary copy addressed here, before the journal sees it (the arrival log, ADR-064 rule 11)."""
        copies = []
        for r in recs:
            try:
                meta = gzmsg.parse(r["content"])["metadata"]
            except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
                continue
            copies.append((str(r.get("id") or r.get("seq")),
                           meta.get("MESSAGE-ID") or "sha256:" + hashlib.sha256(r["content"].encode("utf-8", "surrogatepass")).hexdigest()))
        try:
            adapter.relay_arrivals(self._arrivals, self._me["address"], copies)
        except OSError as e:
            # Evidence for the parity report, not a condition of delivery.
            print(f"gzcoord: the arrival log could not be written ({e.strerror or e}); the message is shown", file=sys.stderr)

    def health(self) -> list[Health]:
        return [self.primary.health(), *(m.health() for m in self.mirrors)]

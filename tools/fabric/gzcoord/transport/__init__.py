"""tools/fabric/gzcoord/transport/ — the one owner of message delivery (agent-fabric ADR-067, message-transport in
tools/fabric/mechanisms.json). A carrier adapter import anywhere else needs a reason in tools/fabric/transport-calls.json
(tools/fabric/transport_calls.py).

`open_transport` is the one factory: the inbox and the sender take a TransportMux from it and name no transport. Since the
transport cutover plan's W15 there is one transport, the InterWeave carrier (CarrierPrimary): no relay is built, called or
mirrored to, and the account's transport mode (mode.py) no longer chooses between transports here. The presence check before
an addressed send is the control plane's (control/presence.py) and is not this module's.

With the journal off (ADR-064 rule 8, D7 of the cutover plan) a SEND goes through the carrier as always and the sender's bypass
line says the journal is off; receiving with the journal off is refused: the carrier does not run without a journal, so there
is nothing to receive from, and the human relay is the break-glass."""
from __future__ import annotations

from typing import Callable

from .base import Health, Primary, Sent, Transport
from . import mode
from .carrier import CarrierPrimary, CarrierTransport
from .mux import TransportMux

__all__ = ["CarrierPrimary", "CarrierTransport", "Health", "ModeError", "Primary", "Sent", "Transport", "TransportMux",
           "mode", "open_transport"]

ModeError = mode.ModeError


def open_transport(*, me: dict, journal_off: bool = False, state_dir: str | None = None,
                   iso_now: Callable[[], str] | None = None,
                   journal_newest: Callable[[int], list[dict]] | None = None, record_only: bool = False,
                   for_send: bool = False) -> TransportMux:
    """`me` is the login's identity (its `address` is the consumer and the sender). `state_dir` and `iso_now` give the receiving
    side its shown ledger; without them the mux only sends. `journal_newest` is what the carrier's `newest` reads
    (inbox_parts.records.journal_newest over the account's journal); without it the carrier cannot answer `newest`.
    `record_only` is the read of the record (--replay, --history): no logs. `journal_off` with `for_send` is a send's route;
    `journal_off` alone is a receive's, refused with ModeError, which a caller says in one line."""
    if journal_off and not for_send and not record_only:
        raise ModeError("receiving with GZCOORD_JOURNAL=off is refused: the carrier starts only with a journal "
                        "(ADR-064 rule 8); the human relay is the break-glass")
    return TransportMux(CarrierPrimary(address=me["address"], journal_newest=journal_newest), me=me,
                        state_dir=None if record_only else state_dir, iso_now=iso_now)

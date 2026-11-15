"""tools/fabric/gzcoord/transport/ — the one owner of message delivery (agent-fabric ADR-067, message-transport in
tools/fabric/mechanisms.json). A relay call or a carrier adapter import anywhere else needs a reason in
tools/fabric/transport-calls.json (tools/fabric/transport_calls.py).

`open_transport` is the one factory: the inbox and the sender take a TransportMux from it and name no transport. Which
transports there are is decided here and nowhere else, by the account's transport mode (mode.py), carried on the mux as
`.mode`:

  relay-record   the relay of the project's integration config is the primary (ADR-064 rule 11), the second carrier a mirror
  carrier-record the carrier is the primary and the relay a mirror, sent to and read beside it
  carrier-only   the carrier alone: no relay transport is built, so no transport verb can call one. The presence check before
                 an addressed send is the control plane's (control/presence.py, W12) and still posts to the relay first,
                 with the second carrier's leg under `control_carrier: dual`; that is gate 2's read-back, not this factory's

With the journal off (ADR-064 rule 8, D7 of the cutover plan) a SEND follows the mode's own primary, with no mirror: a mirror's
acceptance writes a journal row, and the journal is what is off; the outbox keeps the text and the sender's bypass line says so.
In relay-record that primary is the relay, as it always was. Receiving with the journal off is refused in the carrier modes: the
carrier does not run without a journal, so there is nothing to receive from, and the human relay is the break-glass. An unreadable mode
raises ModeError; a caller says it in one line and does not guess one."""
from __future__ import annotations

from typing import Callable

from .. import i18n
from .base import Health, Primary, Sent, Transport
from . import mode
from .carrier import CarrierPrimary, CarrierTransport
from .mux import TransportMux
from . import relay as relay_transport
from .relay import RelayMirror, RelayTransport
from .relay import start as _start_hosted

__all__ = ["CarrierPrimary", "CarrierTransport", "RelayMirror", "Health", "ModeError", "Primary", "RelayTransport", "Sent", "Transport", "TransportMux",
           "mode", "open_transport", "start_hosted"]

ModeError = mode.ModeError


def start_hosted(cfg: dict, t: i18n.Printer | None = None) -> dict:
    """The primary's own start, before there is anything to send (the hosting working copy brings its relay up); a client
    returns {"hosted": False, "started": False} at once."""
    return _start_hosted(cfg, t)


def open_transport(cfg: dict | None, *, token: str, me: dict, journal_off: bool = False, state_dir: str | None = None,
                   iso_now: Callable[[], str] | None = None,
                   journal_newest: Callable[[int], list[dict]] | None = None, record_only: bool = False,
                   for_send: bool = False) -> TransportMux:
    """`cfg` is the project's integration config (inbox_parts.config.integration_config) and must be a configured one
    wherever a relay is built (None is for carrier-only alone); `me` the login's identity (its `address` is the consumer and
    the sender). `state_dir` and `iso_now` give the receiving side its logs; without them the mux only sends. `journal_newest`
    is what the carrier's `newest` reads (inbox_parts.records.journal_newest over the account's journal); without it the
    carrier as primary cannot answer `newest`. The mode is read from `state_dir` when given, else from the account's own
    state directory. `record_only` is the read of the record (--replay, --history): the primary alone, no mirror, no logs, in
    whatever mode the account is in. `journal_off` with `for_send` is a send's route (above); `journal_off` alone is a
    receive's, refused in the carrier modes."""
    account_mode = mode.read(state_dir)["mode"]
    if journal_off and not for_send and not record_only and account_mode != mode.RELAY_RECORD:
        raise ModeError(f"transport mode {account_mode} has no receiving with GZCOORD_JOURNAL=off: the carrier starts only with a "
                        "journal (ADR-064 rule 8); the human relay is the break-glass")
    relay_leads = account_mode == mode.RELAY_RECORD
    relay = None
    if relay_leads or (account_mode == mode.CARRIER_RECORD and not record_only and not journal_off):
        if cfg is None:
            raise ModeError(f"transport mode {account_mode} needs the project's relay configuration")
        relay = RelayTransport(cfg["relay_url"], cfg["channel"], me["address"], token,
                               call_timeout=None if relay_leads else relay_transport.MIRROR_CALL_S)
    if relay_leads:
        mux = TransportMux(relay, [] if journal_off or record_only else [CarrierTransport()], me=me, state_dir=state_dir,
                           iso_now=iso_now)
    else:
        carrier = CarrierPrimary(address=me["address"], journal_newest=journal_newest)
        mux = TransportMux(carrier, [RelayMirror(relay)] if relay is not None else [], me=me, state_dir=state_dir,
                           iso_now=iso_now)
    mux.mode = account_mode
    return mux

"""tools/fabric/gzcoord/transport/ — the one owner of message delivery (agent-fabric ADR-067, message-transport in
tools/fabric/mechanisms.json). A relay call or a carrier adapter import anywhere else needs a reason in
tools/fabric/transport-calls.json (tools/fabric/transport_calls.py).

`open_transport` is the one factory: the inbox and the sender take a TransportMux from it and name no transport. Which
transports there are is decided here and nowhere else: the relay of the project's integration config is the primary
(ADR-064 rule 11), the second carrier a mirror unless the journal is off (rule 8). Moving the primary is a change to this
factory.

The account's transport mode (mode.py) is read here and carried on the mux as `.mode`. Until W6 to W8 give the modes their
own transports, all three build the one mux below: the mode is a fact the operator can set and read, not yet a choice of
transport. An unreadable mode raises ModeError; a caller says it in one line and does not guess one."""
from __future__ import annotations

from typing import Callable

from .. import i18n
from .base import Health, Primary, Sent, Transport
from . import mode
from .carrier import CarrierTransport
from .mux import TransportMux
from .relay import RelayTransport
from .relay import start as _start_hosted

__all__ = ["CarrierTransport", "Health", "ModeError", "Primary", "RelayTransport", "Sent", "Transport", "TransportMux",
           "mode", "open_transport", "start_hosted"]

ModeError = mode.ModeError


def start_hosted(cfg: dict, t: i18n.Printer | None = None) -> dict:
    """The primary's own start, before there is anything to send (the hosting working copy brings its relay up); a client
    returns {"hosted": False, "started": False} at once."""
    return _start_hosted(cfg, t)


def open_transport(cfg: dict, *, token: str, me: dict, journal_off: bool = False, state_dir: str | None = None,
                   iso_now: Callable[[], str] | None = None) -> TransportMux:
    """`cfg` is the project's integration config (inbox_parts.config.integration_config) and must be a configured one;
    `me` the login's identity (its `address` is the consumer and the sender). `state_dir` and `iso_now` give the receiving
    side its logs; without them the mux only sends. The mode is read from `state_dir` when given, else from the
    account's own state directory."""
    account_mode = mode.read(state_dir)["mode"]
    primary = RelayTransport(cfg["relay_url"], cfg["channel"], me["address"], token)
    mux = TransportMux(primary, [] if journal_off else [CarrierTransport()], me=me, state_dir=state_dir, iso_now=iso_now)
    mux.mode = account_mode
    return mux

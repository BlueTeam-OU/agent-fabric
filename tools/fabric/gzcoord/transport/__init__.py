"""tools/fabric/gzcoord/transport/ — the one owner of message delivery (agent-fabric ADR-067, message-transport in
policies/mechanisms.json). A relay call or a carrier adapter import anywhere else needs a reason in
policies/transport-calls.json (tools/fabric/transport_calls.py).

`open_transport` is the one factory: the inbox and the sender take a TransportMux from it and name no transport. Which
transports there are is decided here and nowhere else: the relay of the project's integration config is the primary
(ADR-064 rule 11), the second carrier a mirror unless the journal is off (rule 8). Moving the primary is a change to this
factory."""
from __future__ import annotations

from typing import Callable

from .. import i18n
from .base import Health, Primary, Sent, Transport
from .carrier import CarrierTransport
from .mux import TransportMux
from .relay import RelayTransport
from .relay import start as _start_hosted

__all__ = ["CarrierTransport", "Health", "Primary", "RelayTransport", "Sent", "Transport", "TransportMux",
           "open_transport", "start_hosted"]


def start_hosted(cfg: dict, t: i18n.Printer | None = None) -> dict:
    """The primary's own start, before there is anything to send (the hosting working copy brings its relay up); a client
    returns {"hosted": False, "started": False} at once."""
    return _start_hosted(cfg, t)


def open_transport(cfg: dict, *, token: str, me: dict, journal_off: bool = False, state_dir: str | None = None,
                   iso_now: Callable[[], str] | None = None) -> TransportMux:
    """`cfg` is the project's integration config (inbox_parts.config.integration_config) and must be a configured one;
    `me` the login's identity (its `address` is the consumer and the sender). `state_dir` and `iso_now` give the receiving
    side its logs; without them the mux only sends."""
    primary = RelayTransport(cfg["relay_url"], cfg["channel"], me["address"], token)
    return TransportMux(primary, [] if journal_off else [CarrierTransport()], me=me, state_dir=state_dir, iso_now=iso_now)

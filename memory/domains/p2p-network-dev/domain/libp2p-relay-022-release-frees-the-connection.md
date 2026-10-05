---
role: "p2p-network-dev"
class: domain
topic: "libp2p-relay-022-release-frees-the-connection"
description: "libp2p-relay 0.22.0's client resets a reservation when its listener closes, so a released reservation's connection idles out; 0.21.1 held and renewed it for up to an hour"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 76443ac5ecde347a
---

## libp2p-relay 0.22.0's client resets a reservation when its listener closes, so a released reservation's connection idles out; 0.21.1 held and renewed it for up to an hour

In libp2p-relay 0.22.0 (client), `remove_listener` → `FromSwarm::ListenerClosed` →
`Behaviour::on_listener_closed` (`priv_client.rs:173-205`) sends
`handler::In::ResetReservation` to the reservation's connection; the handler sets
`reservation = None` (`priv_client/handler.rs:255-257`) and `connection_keep_alive`
becomes false (`:267-269`). So a released reservation stops renewing, and its
connection closes at the Swarm's idle timeout unless another handler (gossipsub mesh,
live circuit streams) keeps it open. On the SERVER side, 0.22.0's
`behaviour.rs` `on_connection_closed` removes the peer's reservation and emits
`ReservationClosed` when that connection goes, so the slot is freed at the close,
not at the reservation's own expiry (read by architect-cto, 2026-09-25). In 0.21.1 there was no `on_listener_closed`: the
handler kept the reservation and renewed it for up to an hour. Relay v2 frees the
relay's slot when that connection closes.

Consequence (InterWeave #115, closed unmerged 2026-09-25): force-closing the
"control connection" on release is both unnecessary at 0.22.0 and harmful, since the
only connections still open are those carrying a data plane or circuits. A dial
origin (`RelayReservation`) is also no way to identify a reservation's connection:
the client reuses any existing connection to the relay, and its circuit-setup
dials carry the same origin.

**Why:** a crate bump silently obsoleted a fix written against the older version;
the fix sat unmerged six days and was reviewed against its own premise.
**How to apply:** before landing an old branch, re-read the pinned crate at the
lines the branch's premise cites. Related: [[libp2p-relay-client-listener-semantics]]
(0.21.1-era, still accurate for the listener events).

*References: libp2p-relay-client-listener-semantics*

*Observed 2026-09-25 (p2p-network-dev)*

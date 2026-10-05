---
role: "p2p-network-dev"
class: domain
topic: "libp2p-relay-client-listener-semantics"
description: "What libp2p-relay 0.21.1's client actually reports for a reservation -- addresses are the relay's external ones, one NewListenAddr each, re-emitted on renewal; every failure and a release alike end in ListenerClosed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 41aaeac9dd367b67
---

## What libp2p-relay 0.21.1's client actually reports for a reservation -- addresses are the relay's external ones, one NewListenAddr each, re-emitted on renewal; every failure and a release alike end in ListenerClosed

libp2p-relay 0.21.1 `client::Behaviour`, measured while building InterWeave's relay adapter (2026-09-18, `crates/transport/libp2p/src/runtime/relay_driver.rs`):

- A reservation is obtained by `listen_on(<relay-addr>/p2p/<relay>/p2p-circuit)`. If the client holds no direct connection to the relay it emits `ToSwarm::Dial` for the relay's DIRECT address (a behaviour dial — route 1 — attributable); if it does, the reservation rides the existing connection with no dial at all.
- An accepted reservation's addresses are the RELAY's own external addresses (from `ExternalAddresses` on the server), each suffixed `/p2p-circuit/p2p/<local>`, surfaced as one `NewListenAddr` per address, and re-emitted on every renewal. No batch boundary, no `ExpiredListenAddr` for any of them. A relay with no external address makes the listener close with `NoAddressesInReservation` (SPIKE-004 note 10).
- The client also pushes its own `ExternalAddrConfirmed` for the address it was asked to listen on — swallow it if policy owns the advertised set.
- EVERY end of an ask is `ListenerClosed`: a gate-refused dial (synchronous `DialFailure` drops the listener's channel → `Ok(())` reason), a failed dial, a refused or timed-out reservation (`Err`), a closed relay connection, AND the caller's own `remove_listener` (also `Ok(())`). A driver must remember the listener ids it removed itself, or a release reads as a loss.
- The behaviour's `ReservationReqAccepted{renewal}` event says the exchange happened; the addresses come only through the listener.
- `SwarmBuilder::with_relay_client` composes transport and behaviour together; branching the builder on the config (`with_relay_client` only when configured) yields the same `Swarm<B>` type from both arms, so a default profile composes no relay transport.

**Why:** the first manager design held one address per reservation and would have read the relay's second external address as a supersession; every reviewer risk about "Requested never expires" is answered by the listener-close list above.
**How to apply:** an adapter keys acceptance on `NewListenAddr` (not the behaviour event), holds a bounded address list per reservation, and tracks released listener ids. See [[stage-11-pr84-landed]].

*References: stage-11-pr84-landed*

*Observed 2026-09-18 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "libp2p-facts-from-the-hop-gate-and-keepalive"
description: "libp2p 0.57 facts that bit building the relay hop gate, close-on-removal and the relay keepalive (#129) — outbound local IP, ping's give-up, relay's per-connection ReservationClosed, pub(crate) handler events"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8a85afcac9c8d19d
---

## libp2p 0.57 facts that bit building the relay hop gate, close-on-removal and the relay keepalive (#129) — outbound local IP, ping's give-up, relay's per-connection ReservationClosed, pub(crate) handler events

Measured or read while building PR #129 (2026-09-26), pinned libp2p 0.57 (swarm 0.48, relay 0.22, ping 0.48, tcp 0.45):

- **An outbound connection's local address is reported nowhere** (ConnectedPoint::Dialer has only the remote). libp2p-tcp 0.45 binds every dial to the UNSPECIFIED address (port reuse only), so the kernel's route source toward the remote (UDP connect, no packet) is the same decision. A /dns dial exposes no resolved IP at all.
- **listen_protocol is consulted per inbound stream** (swarm connection.rs:440), so a handler can refuse per request; but relay 0.22 reads RESERVE/CONNECT up to 60 s after negotiation, so a gate must be re-read where the request reaches the behaviour.
- **relay 0.22's handler events are pub(crate)**: a wrapper can recognise ReservationReqReceived/CircuitReqReceived only by Debug form ("Left(Event::...") — pin it with a counter a wire test asserts.
- **relay 0.22 emits ReservationClosed for EVERY closed connection of a peer**, reservation or not (behaviour.rs:406-437); count holders by "no connection left", not per event.
- **ping 0.48's handler gives up forever on a first Unsupported** and always pings too; so every end should answer, and pinging is switched separately. Its streams call ignore_for_keep_alive — an echo must too, or it keeps idle connections open.
- **A missed ping takes interval + timeout + the swarm's 10 s upgrade timeout** (the second failure is a fresh stream's negotiation).
- **An unpolled Swarm still answers** with the tokio executor (connections run in their own tasks); to kill a path without an event, put a silenceable TCP proxy in it.
- **Identify notifies every handler on an external-address change**, which re-polls connections, so protocol-set changes driven by that change need no extra waker.
- A client that closes its end of a dead path cannot tell the relay: the relay must ping its reservation holders or it refuses the rebuild for per-peer room.

Related: [[spike-004-phase-b-node-rows]].

*References: spike-004-phase-b-node-rows*

*Observed 2026-09-26 (p2p-network-dev)*

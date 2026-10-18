---
role: "p2p-network-dev"
class: domain
topic: "domain-libp2p-relay-circuit-canceled-is-the-hops"
description: "libp2p-relay client: a circuit asked for before its connection to the relay is up is dropped unsent (ResponseFromBehaviourCanceled) — score it as the relay hop's, not the destination peer's, whatever the connection table says at settlement"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 9ea8e65d6be28470
---

## libp2p-relay client: a circuit asked for before its connection to the relay is up is dropped unsent (ResponseFromBehaviourCanceled) — score it as the relay hop's, not the destination peer's, whatever the connection table says at settlement

Measured on InterWeave (libp2p 0.57: libp2p-relay 0.22.0, libp2p-swarm 0.48), #245/#247:
- A daemon that dials a `/p2p-circuit` route at start, a few ms before its own connection to the relay is
  up, gets a failed dial. The relay client asks for the hop, its own dial to the relay is refused while the
  reservation's dial to the same relay is in flight, and it drops the circuit request UNSENT: the error is
  `ResponseFromBehaviourCanceled`. The relay never saw the request.
- After a restart the same race shows a different face: by the time the failure is settled the relay IS
  connected (24 ms earlier in the measured run; the swarm delivers the relay's ConnectionEstablished before
  the circuit's failure). A "relay not connected → hop's fault" check misses it and backs the DESTINATION
  off (30 s), so a relay-only peer is unreachable for 30 s after every start or restart, 1 run in 3.

Fix shape: classify by the error, not by the connection table — a transport failure of a RelayCircuit dial
that never reached its relay (no direct connection to the relay, or the canceled request) ranks the address
down, backs no peer off and keeps the route; WrongPeerId and other non-transport errors keep their scoring.

**How to apply:** when a failure's attribution depends on "was X connected", print the actual dial error
first (logs saying only `dial_failed` cannot separate the cases), and check whether the state could have
changed between the failure and its settlement. Related: [[domain-retry-trigger-is-an-edge]].

*References: domain-retry-trigger-is-an-edge*

*Observed 2026-10-15 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "dialer-established-precedes-listener-auth"
description: "A libp2p dialer reports ConnectionEstablished before the listener authenticates it; a test must not assume which arriving dialer a listener-side ceiling refuses"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - be0bb3a246314ae3
---

## A libp2p dialer reports ConnectionEstablished before the listener authenticates it; a test must not assume which arriving dialer a listener-side ceiling refuses

libp2p's SwarmBuilder upgrades TCP with multistream-select `V1Lazy` (libp2p 0.56 and 0.57,
`builder/phase/tcp.rs`). Noise XX also finishes on the initiator first. So a dialer's
`ConnectionEstablished` arrives before the listener has authenticated that connection.

Dialing sequentially and waiting for the dialer's event does not order the listener's
decisions. Under CPU load the listener authenticates them in a different order. In InterWeave's
peer_limits test, a connected-peer ceiling of 2 refused dialer 0 or 1 instead of dialer 2 in
about 2% of runs. A test that then indexed dialers[0] as "the held one" failed.

A test should read which dialers the listener kept from `Swarm::is_connected` on each dialer,
never from the dial order. InterWeave commit 037727cc does this.

**Why:** that failure cost a PR's CI on a change outside the crate (InterWeave#283).

**How to apply:**
- In any ceiling, rate or first-come test, take the oracle from the subject's decision.
- When diagnosing a flake under load, record a cheap history (push to a Vec, print only on panic).
  Do not add driving loops or sleeps: the extra time changes the race. In this case 500 runs with
  added driving showed no failure, which wrongly suggested the hypothesis was false.

*Observed 2026-10-16 (p2p-network-dev)*

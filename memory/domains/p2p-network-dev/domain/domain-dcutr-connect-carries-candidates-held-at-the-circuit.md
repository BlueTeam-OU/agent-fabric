---
role: "p2p-network-dev"
class: domain
topic: "domain-dcutr-connect-carries-candidates-held-at-the-circuit"
description: "libp2p-dcutr fills CONNECT from candidates held when the relayed connection comes up; a test peer must be observed first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - c52dc21a1df86bcb
---

## libp2p-dcutr fills CONNECT from candidates held when the relayed connection comes up; a test peer must be observed first

libp2p-dcutr 0.15 builds the relayed connection's handler with
`observed_addresses()` AT ESTABLISHMENT, and those candidates come only from
`NewExternalAddrCandidate`, which a plain peer gets from a remote's Identify
(the relay's). Nothing orders that Identify round trip before a circuit, so a
test peer that dials or listens over a circuit at once can send a CONNECT with
no address (the other side fails "Outbound stream error: Protocol error",
NoAddresses) or with only a scripted candidate. Seen under a loaded full suite
on InterWeave dcutr.rs (2026-10-26); reproduced deterministically by
`add_external_address(listen addr)` first, since the Swarm skips delivering a
candidate it already confirmed. Fix: wait for `SwarmEvent::NewExternalAddrCandidate`
on the expected IP — the Swarm emits it after every behaviour got it. Dial the
relay first and wait: a circuit dial while the relay dial is still pending is
cancelled (ResponseFromBehaviourCanceled). Commit 5d7ca521 (j79).
Related: [[domain-a-test-waits-for-the-state-it-presumes]], [[domain-libp2p-relay-circuit-canceled-is-the-hops]].

*References: domain-a-test-waits-for-the-state-it-presumes, domain-libp2p-relay-circuit-canceled-is-the-hops*

*Observed 2026-10-27 (p2p-network-dev)*

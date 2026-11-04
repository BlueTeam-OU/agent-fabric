---
role: "p2p-network-dev"
class: solution
topic: "interweave-broadcast-order-not-preserved"
description: "InterWeave signed-GossipSub broadcast does not preserve one publisher's order; a burst can arrive reordered"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b4612ff7f95c1ab
---

## InterWeave signed-GossipSub broadcast does not preserve one publisher's order; a burst can arrive reordered

A burst of 200 broadcasts from one publisher to one receiver arrived out of the publisher's order in 1 of about 13 runs (2026-10-19, two daemons on loopback). So no test or client document may assert broadcast order. The broadcast-burst case in tests/automated-client prints whether order held and asserts only "each once" (commit 4db37607). 36-41 of 200 were delivered per run under the ingress bucket (32 burst, 120/min). Direct sends retried through Overloaded delivered 200/200 in about 84 s. Related: [[interweave-session-loss-errors]].

*References: interweave-session-loss-errors*

*Observed 2026-10-19 (p2p-network-dev)*

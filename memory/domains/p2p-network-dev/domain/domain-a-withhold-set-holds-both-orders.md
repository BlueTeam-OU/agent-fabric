---
role: "p2p-network-dev"
class: domain
topic: "domain-a-withhold-set-holds-both-orders"
description: "A set told to a wrapper on one event (a platform view) must be right whichever of two racing sources arrives first; derive it from neither source's presence"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 5d2f766e90827e90
---

## A set told to a wrapper on one event (a platform view) must be right whichever of two racing sources arrives first; derive it from neither source's presence

On #465 (ADR-0052 rule 10), the IP set Identify withholds was recomputed only when a platform view arrived. The view and the listener poll race: Android's if-watch polls every 10 s. There were two attempts:
- **Round 1:** the set was the view's classification only. A classified IP the view dropped while it was still bound was released.
- **Round 2:** I fixed round 1 by deriving the set from bound listeners. That made it leak in the opposite order: an IP classified before its listener binds was released.

Same invariant, two review rounds.

The fix that holds is the union. It contains every classified IP whether bound or not, which covers classify-then-bind. It also contains the bound IPs no longer held, which covers depart-while-bound. Each half gets a test that binds in its own order, and a mutation that removes it.

**Why:** a fix proved against one ordering of two racing sources reopens the other. Write the tests for all orders before writing the fix.

**How to apply:** when a value is pushed to a component on event A and read when event B happens, list every interleaving of A and B: A then B, B then A, B leaving before A. Give each one a test, and make the set's membership independent of which source has reported. See [[domain-a-test-waits-for-the-state-it-presumes]].

*References: domain-a-test-waits-for-the-state-it-presumes*

*Observed 2026-10-26 (p2p-network-dev)*

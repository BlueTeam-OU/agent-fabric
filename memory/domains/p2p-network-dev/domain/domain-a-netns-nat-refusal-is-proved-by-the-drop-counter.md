---
role: "p2p-network-dev"
class: domain
topic: "domain-a-netns-nat-refusal-is-proved-by-the-drop-counter"
description: "In a network-namespace NAT harness a refused direct dial proves the NAT only when a counter on the NAT's forward-drop rule rose; an unrouted core's ICMP unreachable or the NAT's own RST refuses it first and looks the same"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 9ed1cfe95ab21148
---

## In a network-namespace NAT harness a refused direct dial proves the NAT only when a counter on the NAT's forward-drop rule rose; an unrouted core's ICMP unreachable or the NAT's own RST refuses it first and looks the same

A harness of two private networks, each behind its own nft masquerade, and a relay on a core between them
(InterWeave C-05 R7, tests/support/src/e2e/netns.rs) "proved" that a direct dial between the two sides fails.
It did fail, but not at the NAT. A review-class rebuild of the setup under `unshare -Urnm`, with a counter on
the far NAT's drop, showed two other causes:
- The core had no route to either private range. It answered ICMP net-unreachable, the near NAT let that back
  as related, and the connect failed in about 10 ms. The forward-drop rule was never reached.
- The probe of the far NAT's own address went to its INPUT path, not FORWARD, and its own stack answered RST.

The fix: the core routes each private range to its NAT, each NAT's forward chain ends in `counter drop`, and
`inward_drops(nat)` reads the counter. A refused dial must end on the dial timeout AND raise the far NAT's
counter. Two mutations prove it: NAT forwarding inward fails "dialled directly", and the core routes removed
fails "refused in 342µs, not by NatB's drop". The live control is the same-side dial, which connects.

**How to apply:** in any namespace or container NAT topology, give every "refused" assertion an oracle at the
mechanism (a counter on the rule that should refuse), and check how fast the refusal came: milliseconds means
something nearer than the NAT answered. Probe a host behind the NAT, not the NAT's own address.
Related: [[domain-userns-root-is-overflow-uid]], [[nat-trials-need-a-fresh-port-each]].

*References: domain-userns-root-is-overflow-uid, nat-trials-need-a-fresh-port-each*

*Observed 2026-10-22 (p2p-network-dev)*

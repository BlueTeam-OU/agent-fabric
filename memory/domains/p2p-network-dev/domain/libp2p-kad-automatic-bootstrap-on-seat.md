---
role: "p2p-network-dev"
class: domain
topic: "libp2p-kad-automatic-bootstrap-on-seat"
description: "libp2p-kad 0.49 starts a bootstrap 500 ms after any routing seat, even with periodic bootstrap off; a test that seats a full bucket must not let seated routers name competing peers until it is full"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 5191bb6ec0a19573
---

## libp2p-kad 0.49 starts a bootstrap 500 ms after any routing seat, even with periodic bootstrap off; a test that seats a full bucket must not let seated routers name competing peers until it is full

libp2p-kad 0.49.0's `bootstrap::Status` starts a bootstrap `DEFAULT_AUTOMATIC_THROTTLE` (500 ms) after a peer is inserted into the routing table. `set_periodic_bootstrap_interval(None)` disables only the periodic one. The automatic one stays on unless `set_automatic_bootstrap_throttle(None)` is set, and InterWeave's `kademlia_driver::build_behaviour` does not set it. The bootstrap asks the routers already seated and dials whatever they name.

Seen in j92 (PR #310): `kademlia_adversarial`'s full-bucket test seated 8 honest routers that already named 2 trusted newcomers. A bootstrap during seating dialled and seated the newcomers while the bucket still had room, so the last honest router was never seated (3 failures in 6 runs). The fix: the routers learn the newcomers by `Order::Know` only after the bucket is full.

**How to apply:** in any test that fills a bucket, or orders seats, a peer named by a seated router can take a seat before the test's own dial lands. Withhold the names until the premise is built. Do not rely on seat timing.

*Observed 2026-10-19 (p2p-network-dev)*

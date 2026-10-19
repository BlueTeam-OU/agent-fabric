---
role: "p2p-network-dev"
class: domain
topic: "a-mirroring-store-takes-the-providers-shape-and-aging"
description: "Two bounded stores that hold views of the same peers must agree in SHAPE (peers x per-peer, not a total pair count) and in AGING (one store owns when an entry is forgotten), with every exit through one function — otherwise eviction rules…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fbeeb368caf763a0
---

## Two bounded stores that hold views of the same peers must agree in SHAPE (peers x per-peer, not a total pair count) and in AGING (one store owns when an entry is forgotten), with every exit through one function — otherwise eviction rules fail review round after round

Seen twice in InterWeave, each after three to five review rounds on one
invariant:

- **Shape.** A vendored mDNS store capped at 2048 (peer, addr) pairs of any
  shape sat under a provider holding 256 peers x 8 addresses. Single-address
  peers filled 2048 slots while the provider kept 256, so 1792 crate records
  were ones the provider had refused, and evicting one freed nothing
  downstream. Ruling (DECISION 01a0d8d7): cap by the provider's shape — 256
  peers and 8 per peer, drift-checked against its constants.
- **Aging.** A per-peer address book (max 8) aged separately from a pruned,
  LRU policy table holding each address's success/failure state. Any eviction
  rule that read policy state was defeated by pruning: a working route looked
  never-worked and went first; pruned failure counts made a dead full book
  refuse a moved peer's new address. Fix was a decision that the book owns
  its aging, not a sixth patch; every way out (evict, retire, permanent
  failure, hand-over) then goes through one function and the docs list them.
- **Order.** When a capped store evicts and inserts in one step, deliver the
  eviction's Expired before the replacement's Discovered, or a downstream
  store at capacity drains.

**How to apply:** when a store mirrors or feeds another, write down whose
bound and whose clock is authoritative before the first eviction rule; on a
second review round failing the same eviction invariant, look for the split
state and ask its owner for that decision.

*Observed 2026-10-18 (p2p-network-dev)*

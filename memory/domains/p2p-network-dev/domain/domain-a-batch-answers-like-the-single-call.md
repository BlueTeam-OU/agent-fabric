---
role: "p2p-network-dev"
class: domain
topic: "domain-a-batch-answers-like-the-single-call"
description: "Designing an all-or-none batch form of an existing write: same check order, rule by rule across every item, held items count nothing against a size bound, and a client short-circuit must name the item the server would"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 34a21450c4996e5c
---

## Designing an all-or-none batch form of an existing write: same check order, rule by rule across every item, held items count nothing against a size bound, and a client short-circuit must name the item the server would

InterWeave's admin.peers.add_addresses (IPC 2.9) was built and ruled to these rules (ADR-0062 A 2026-10-22 iii):
- **A one-item batch answers exactly as the single call.** Use the single call's check order. Apply each rule to
  EVERY item before the next rule (every line's grammar, then the provider, then every line's special-use floor,
  then the bound), so the item named is deterministic. A rule that refuses the whole list (provider_disabled)
  carries no index.
- **The size bound counts only what the store would gain.** An item already held, or repeated earlier in the
  batch, is answered `unchanged` and counts nothing. The bound is the store's size, and the single call already
  answers a held item `unchanged` at the limit. A rescan of a known code is then never refused `bound`.
- **A client-side short-circuit must give the server's answer, including which item it names.** For one item,
  answer locally what the server would: an over-long line is `grammar` on add, but `unchanged` on remove, since
  nothing that long can be stored. In a list, refusing locally would name the wrong line. So send a placeholder
  that is inside the size bound and outside the grammar, and let the server name the first failing line.
- **Index base is part of the contract.** The doc's example "line 1" read as 1-based against a 0-based `index`,
  and it drew a review finding (#393 F4). Say "the second line (index 1, counted from 0)".

**How to apply:** pin all of these in the shared conformance case at every binding. Include an order control per
rule pair (e.g. `[own, garbage]` -> grammar at index 1, `[loopback, own]` -> own_peer at index 1).

*Observed 2026-10-25 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "domain-a-staleness-refusal-is-checked-last"
description: "Ordering lost/late writes across connections with a last-applied stamp per key: check the stale refusal last, count an unchanged write as applied, bound the memory so it fails closed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 169c93ce2af40c94
---

## Ordering lost/late writes across connections with a last-applied stamp per key: check the stale refusal last, count an unchanged write as applied, bound the memory so it fails closed

The design (InterWeave IPC 2.10 `superseded`, architect-cto DECISION 01a166c9 and REPLY 01a169f6) refuses a
write from a connection older than the one whose write for the same key was last applied. Its parts generalise
to any last-writer guard:
- **Check it LAST**, after every other rule. Then the name covers only a write that would otherwise have taken
  effect, and the audit line records only those. I first wrote "after grammar, before the rest". The code was
  right to put it last, and the record took that.
- **An `unchanged` answer counts as applied.** That write's intent is the state that stands, so a later, older
  write must not undo it. A refusal by another rule stamps nothing.
- **Stamp where the writing port opens**, counting only ports that can write. A status or shutdown port would
  otherwise order writes it never makes.
- **Bound the map** by pruning an entry once no open writing port is older than it. Give it a ceiling whose
  evicted stamp becomes a floor: a write older than the floor is refused for every key. It fails closed and never
  applies late.
- **Reads stay unordered.** State that limit in the contract and pin it with a test, so a change is noticed.

**How to apply:** when a write can outlive its connection (a buffered frame, an abort after dispatch, a deadline
that discards the outcome but not the call), reach for this shape before a client token (a wire change). Do not
serialise connections either. Related: [[admin-call-order-across-connections]],
[[domain-a-new-refusal-gets-a-down-level-answer]].

*References: admin-call-order-across-connections, domain-a-new-refusal-gets-a-down-level-answer*

*Observed 2026-10-25 (p2p-network-dev)*

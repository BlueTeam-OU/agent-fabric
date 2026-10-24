---
role: "architect-cto"
class: domain
topic: "reflection-a-mirrored-bound-copies-each-dimension"
description: A store meant to stay consistent with a bounded provider copies every dimension of the bound, per key and total, not the product alone, since equal in count is not equal in shape; eviction then frees exactly the slot the provider would free
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8d44fb8ed681f2b2
---

## A store meant to stay consistent with a bounded provider copies every dimension of the bound, per key and total, not the product alone, since equal in count is not equal in shape; eviction then frees exactly the slot the provider would free

InterWeave ADR-0053 rule 2, 2026-09-24: "the crate caps 2048 pairs
of ANY shape, the provider 256 peers x 8" (01a0d8d5-185a); DECISION
01a0d8d7-3133: "equal in count is not equal in shape… three rounds on
one invariant". The design fact behind
[[reflection-a-p2-every-round-on-a-new-shape-means-the-adr-has-no-design]].

*References: reflection-a-p2-every-round-on-a-new-shape-means-the-adr-has-no-design*

*Observed 2026-10-23 (architect-cto)*

---
role: "architect-cto"
class: domain
topic: "reflection-fixture-invariant-checks-derivation-not-plausibility"
description: A test over generated data recomputes each value from its source and compares; a check that a value looks right lets systematically wrong output through
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - fa2afa416a38a6e2
---

## A test over generated data recomputes each value from its source and compares; a check that a value looks right lets systematically wrong output through

gzapp romanisation fixtures, 2026-09-18: "four checks that asked
whether a string looked right and none whether it was the romanisation
of anything" (01a0b176-57eb); the defect they missed was not the fold,
"THE SPACES DOUBLE TOO" (01a0b175-b4f4); db-admin had "verified it by
what the aliases SAY" (01a0b1a2-a992). The specific invariant is in
ADR-035's history (amendment of 2026-09-18); this is the general form.
Near [[test-a-derivation-rule-against-the-history-it-governs]], a
different claim.

*References: test-a-derivation-rule-against-the-history-it-governs*

*Observed 2026-10-22 (architect-cto)*

---
role: "architect-cto"
class: domain
topic: "reflection-a-test-asserting-returns-nothing-proves-little"
description: "A test asserting a query returns the empty set passes for any predicate that matches nothing; pin a predicate with an exact-set assertion over a fixture holding known positives and negatives, and close a test-strength finding only when…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 6fce9ae597d75010
---

## A test asserting a query returns the empty set passes for any predicate that matches nothing; pin a predicate with an exact-set assertion over a fixture holding known positives and negatives, and close a test-strength finding only when the named mutation turns the named test red

gzapp 2026-09-19: "reverting 0055's guard to draft 2 leaves the suite
green" (01a0b73a-9781); "asserted that a query returns nothing, which
is the weakest shape a test can have" (01a0b740-0dd8); "two independent
controls, each reddening exactly this test by name" (01a0b754-89c6);
widget tests building the state directly so "these mutations break
nothing" then "all three mutations now red" (01a0b4ea-2ebc,
01a0b501-e790). No CLAUDE.md or skill states it (checked 2026-10-23).
Beside [[reflection-fixture-invariant-checks-derivation-not-plausibility]].

*References: reflection-fixture-invariant-checks-derivation-not-plausibility*

*Observed 2026-10-23 (architect-cto)*

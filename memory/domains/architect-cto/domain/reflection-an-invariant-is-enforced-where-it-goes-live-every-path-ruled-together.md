---
role: "architect-cto"
class: domain
topic: "reflection-an-invariant-is-enforced-where-it-goes-live-every-path-ruled-together"
description: An invariant that must hold when something goes live is checked at that change, not only at creation or import, because the set it is checked against can change in between; and every way into and out of that state is ruled in one ruling…
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4d4b407b5c1ac329
  - 5b925ddd7897fc61
---

## An invariant that must hold when something goes live is checked at that change, not only at creation or import, because the set it is checked against can change in between; and every way into and out of that state is ruled in one ruling, or review finds each missed path in a separate round

gzapp DECISIONs 2026-10-08..10: "the active locale set can change
between create and publish… publish is the one that binds"
(…39d3a9acae8a); "city activation refuses while the head does not cover
the city's dataset" (…fa1f9c7b0d22); "Reactivation… is refused with the
same 409", found by review after the retire path had been
(…d04cb669e8d1, …9f3fc0626242).
**2026-10-25 instance (gzapp ADR-044):** I wrote 'no older binary ever writes under a migration' as a property of compose gating; compose orders starts, not stops, and no release script existed. A rule that needs a step nobody performs is a procedure to build, named with its owner, not a property to assert.

*Observed 2026-10-25 (architect-cto)*

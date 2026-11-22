---
role: "backend-dev"
class: domain
topic: "k-suppression-holds-across-responses"
description: "Designing an aggregate read with small-cell (k) suppression — the property must hold across every response a caller can combine, not per response; serve fixed disjoint closed tiles, stable against writers and sweeps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 255c79e03daa041d
---

## Designing an aggregate read with small-cell (k) suppression — the property must hold across every response a caller can combine, not per response; serve fixed disjoint closed tiles, stable against writers and sweeps

Suppressing every cell below k in each response does not keep a cell below k
from being disclosed. A caller can subtract one response from another, so the
rule has to hold over every set of responses a caller can combine. Four ways it
leaked on one PR:
- **Overlapping windows.** [H-3,H-1) minus [H-2,H-1) gives a one-hour cell that a
  direct read would suppress. Whole-hour windows bound a slice's width, not how
  many slices there are.
- **The same window read twice** across a retention sweep, or after a late
  insert, differences to the rows that changed. Two reads that differ by one row
  expose a cell of size one.
- **Columns forced together.** CHECKs or writer logic can force columns together
  (no vehicle ⇒ disagrees, a preference ⇒ an official stop). Two served marginals
  then subtract to a hidden cell inside one response.
- **Two k values.** If two hosts serve the same data at different k, one host
  serves partitions the other suppresses.

**Why:** gzapp #1160/#1169 (13a/13b), 2026-10-24/25. The blind review found the
first leak (F1, P2) and architect-cto ruled that the rule is cross-response
(DECISION 01a1702b). The second came in as a P1 (DECISION 01a170ac): "served the
same ever after" is privacy-bearing only if it is enforced.

**How to apply:** serve fixed, disjoint, closed tiles on a grid. A tile counts as
closed only on the database clock, with a margin that exceeds an enforced writer
deadline (the insert refuses a stale stamp). Serve no tile that a sweep can reach
yet. Collapse forced columns into one split, and check each split's cross with
every split served before it. Bind one k key in every host, and store the k a
rollup was written at. Test the same tile read across a sweep. Related:
[[shadow-evidence-13a-13b]].

*References: shadow-evidence-13a-13b*

*Observed 2026-10-25 (backend-dev)*

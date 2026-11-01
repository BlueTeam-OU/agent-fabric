---
role: "python-dev"
class: workflow
topic: "supplier-dispatches-no-review"
description: "a supplier on a for/ branch runs no review-class review of its own part; Supplier-Review lists its own checks only"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 96324125dc48b2bd
---

## a supplier on a for/ branch runs no review-class review of its own part; Supplier-Review lists its own checks only

ADR-020 §5 rule 11 (A 2026-10-22): when I deliver a part to a caller's for/ branch, I dispatch no blind review of it. Supplier-Review carries my own checks: failing-before runs, mutations, the suite. The caller's single blind review of the folded head is the review. Working from a feat/ branch hides it from the dispatch guard, but the rule still holds (j156, #358 round 4 F5, coordinator INFO seq 497181).

**Why:** one review per folded head; a supplier review is a second, anchored read.
**How to apply:** skip the code-review dispatch for a supplier part; put the mutations and suite result in the Supplier-Review line; state limits in the REPLY so the caller briefs them.

*Anchors: `docs/adr/ADR-020-the-review-class-is-the-review.md`*

*Observed 2026-10-24 (python-dev)*

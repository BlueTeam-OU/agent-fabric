---
role: "fabric-coordinator"
class: solution
topic: "brand-repos-review-differ"
description: "which brand repository arms a decision-record PR without a review-class review, and which takes every gate"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4b4d6368090c711c
---

## which brand repository arms a decision-record PR without a review-class review, and which takes every gate

gzapi.brand is direct (content to main) and its arm.json names
`direct.record_paths` (`^brand/decisions/[^/]+\.md$`): a record-only PR
arms on the owner's word with no review-class review (ADR-019 §5 rule 1,
A 2026-11-05, commit 220585bc). blueteam.brand's arm.json has no `direct`
block at all, though its live policy mode is direct: every PR there,
a lone record included, needs the review of its head, and its merged
content PRs (#1, #6) had one. The difference is deliberate; its remit
(blueteam.brand#4, job j685) is to state it. Closed j615 that way.

*Anchors: `projects/gzapi.brand/integration/gh/arm.json::record_paths`, `tools/fabric/github/arm.py::record_pr`*

*Observed 2026-11-09 (fabric-coordinator)*

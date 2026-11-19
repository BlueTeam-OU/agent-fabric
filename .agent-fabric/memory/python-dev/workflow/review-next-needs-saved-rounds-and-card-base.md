---
role: "python-dev"
class: workflow
topic: "review-next-needs-saved-rounds-and-card-base"
description: "fabric-review next on a PR: save every posted round first, pass the round's own request (not the fix-range one), name card_base; arm --defer takes head8:F labels from the refusal"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 077d101d1a7fedc6
---

## fabric-review next on a PR: save every posted round first, pass the round's own request (not the fix-range one), name card_base; arm --defer takes head8:F labels from the refusal

j125 #613: `fabric-review next REQ --pr N` fails "no round saved" until `fabric-review save N <round> < report` has run for each posted round; give it the previous round's request json (it derives the fix range itself and writes `<req>-rrN.json`, then `fabric-review brief` that); a hand-made fix-range request is refused ("not an ancestor of origin/main") unless `card_base` is the first round's base, and `next` then says "head has not moved".
`fabric-pr arm --defer "<raising head8>:F<n>" "<why>"`, one per open finding, label from the refusal text.
A review of head A does not count for head B: every fix commit, even a P3's, needs its own re-review, so batch fixes before the re-review and carry P3s by the coordinator's word.

**Why:** five rounds on one PR; each re-review costs about 12 minutes.
**How to apply:** collect all fixes of a round into one commit, save the round, then `next`.

*Anchors: `tools/fabric/review_rounds.py::no round saved`*

*Observed 2026-11-14 (python-dev)*

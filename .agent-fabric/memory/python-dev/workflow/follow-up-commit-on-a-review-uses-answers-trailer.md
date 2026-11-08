---
role: "python-dev"
class: workflow
topic: "follow-up-commit-on-a-review-uses-answers-trailer"
description: "a commit answering review findings carries \"Answers: <PR> <labels>\", not \"Kind: work\""
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d8ac6471f9e4dfc9
---

## a commit answering review findings carries "Answers: <PR> <labels>", not "Kind: work"

j98: I committed the F7/F8 fix of #506 with `Kind: work`; the coordinator's fold counted it as work, not review-fix.

**Why:** the arm count is work commits; an answer to a review must not inflate it (ADR-019 §5 rule 3).
**How to apply:** for a follow-up that answers findings, write `Answers: #N F7 F8` in the trailer (the hook stamps Kind: review-fix).

*Observed 2026-11-08 (python-dev)*

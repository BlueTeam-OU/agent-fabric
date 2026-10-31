---
role: "backend-dev"
class: workflow
topic: "fabric-review-rereview-card-base"
description: "A re-review request whose base is not on main needs card_base; finding-adjudication is its own mode"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 115394a036b19b12
---

## A re-review request whose base is not on main needs card_base; finding-adjudication is its own mode

`fabric-review brief` refuses a re-review whose range base is a branch commit not on
origin/main ("base … is not an ancestor of origin/main … name card_base"): the review card
is read from the base. Add `card_base: <the first round's base, a main commit>` to the
request. Judging findings is `mode: finding-adjudication` with `previous_findings:` (a file
numbering every open finding of both engines), one dispatch per head; the `repository:`
field is the working-copy PATH, not owner/repo; `threat_model` must be a list; an objective
that explains a defect is refused as rationale. Learned on gzapp #1142 (2026-10-19), four
review rounds.

**Why:** each refusal costs a render cycle mid-review-loop.

**How to apply:** start every re-review request from the previous one, change range and
previous_findings, keep card_base.

*Anchors: `agent-fabric/tools/fabric/review_brief.py::card_base`*

*Observed 2026-10-20 (backend-dev)*

---
role: "python-dev"
class: workflow
topic: "review-base-must-be-ancestor-merge-main-first"
description: "fabric-pr post-review refuses a report whose pinned base is not an ancestor of the head; merge origin/main into the branch before rendering the brief"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 072c1a136439df7c
---

## fabric-pr post-review refuses a report whose pinned base is not an ancestor of the head; merge origin/main into the branch before rendering the brief

`fabric-review brief` pins base_sha to the current origin/main. If the branch was cut earlier and main moved, `fabric-pr post-review` refuses the report ("base ... is not an ancestor of head") after the whole review has run, and the review is lost. Happened on #364 (j64): fetch, merge origin/main, push, re-render, review again.

**Why:** the refusal comes after ~8 minutes of review class time and a posted-nothing result.

**How to apply:** `git fetch; git merge origin/main; git push` immediately before `fabric-review brief`, then check `git merge-base --is-ancestor origin/main HEAD`. A later push moves the head and voids a posted review and any arm word bound to the old head. Related: [[review-next-needs-card-base-and-json-request]].

*References: review-next-needs-card-base-and-json-request*

*Observed 2026-10-24 (python-dev)*

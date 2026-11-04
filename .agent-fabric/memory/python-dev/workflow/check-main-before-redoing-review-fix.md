---
role: "python-dev"
class: workflow
topic: "check-main-before-redoing-review-fix"
description: "A re-delivered review-fix request may already be on main; check git log -S before editing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - acc5c3bc959cb859
---

## A re-delivered review-fix request may already be on main; check git log -S before editing

j65 (#304 round 3 F2): the request arrived after my earlier commit b8bb38c8 had been folded into main. `git log -S<new text> -- <file>` on origin/main found it; I re-ran the mutation (drop the commonpath clause at tests/stripped_run.py:95; the case failed) and answered with the commit instead of a duplicate.
**Why:** requests are read late; the tree has moved.
**How to apply:** fetch, grep origin/main for the fix, re-prove the mutation, reply with the commit, close the job with --no-artifact.

*Observed 2026-10-19 (python-dev)*

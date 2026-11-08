---
role: "fabric-coordinator"
class: workflow
topic: "merger-job-blocks-on-review-not-merge"
description: "a job whose own step is the arm/merge must not be blocked on pr:<n> before arming — it would wait on itself"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0f5f85bb49eb912
---

## a job whose own step is the arm/merge must not be blocked on pr:<n> before arming — it would wait on itself

A job whose deliverable is my arm of another login's PR (locale carve-out: holder opens, fabric-coordinator merges, policies/AUTHORITY.md "A locale's translations") must not be blocked on `pr:<owner/repo>#<n>` before the arm: that blocker clears only on merge, which waits on me (j617, #489, 2026-11-05). Block it on a clock or the holder's request until I arm; after `fabric-pr arm --any-owner`, `pr:#n` is right.

**Why:** a blocker that waits on my own action never clears, so the job drops off what switch offers.
**How to apply:** before `fabric-jobs block --on pr:…`, ask who merges it; if me, block on a clock until armed. See [[park-a-job-block-not-pause]].

*References: park-a-job-block-not-pause*

*Observed 2026-11-05 (fabric-coordinator)*

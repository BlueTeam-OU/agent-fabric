---
role: "python-dev"
class: workflow
topic: "post-review-pins-the-head-it-sees"
description: "a commit pushed after the last blind review (even comment-only) voids head coverage; finish all edits before posting, and wait on checks with grep -q checks=pending"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cf5707fdf2aa46f1
---

## a commit pushed after the last blind review (even comment-only) voids head coverage; finish all edits before posting, and wait on checks with grep -q checks=pending

`fabric-pr post-review` records the commit the review covered; a later push, even a comment-only fix of a P3, leaves the gate at "head moved past every review" (exit 5) until a re-review of the new range is posted (j109, PR #252).

**Why:** the re-review's own P3 led to a comment-only commit after the post, costing one more review round.
**How to apply:** settle every finding of a round (fix, or drop the claim) and push before `post-review`; if the push comes after, dispatch a re-review of that range. To wait on CI use `while fabric-pr gate N | grep -q checks=pending; do sleep 20; done` in the background (a `grep -qv` loop exits at once). Under eight work commits the owner arms, whatever the request says about merging.

*Observed 2026-10-14 (python-dev)*

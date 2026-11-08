---
role: "architect-cto"
class: workflow
topic: "drain-leftovers-in-a-read-only-checkout-are-stashed-never-discarded"
description: "Drain-written slice edits that block a control-plane fast-forward are stashed under a job-named entry, then merge --ff-only; the stash is the drain owner's evidence"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ac9a9df2448c9dad
---

## Drain-written slice edits that block a control-plane fast-forward are stashed under a job-named entry, then merge --ff-only; the stash is the drain owner's evidence

When `fabric-ctl all upgrade fabric` aborts a fast-forward of a role's
read-only agent-fabric checkout because the drain wrote frontmatter
into slices there, the route is `git stash push -m <job>-drain-leftovers`
then `git merge --ff-only origin/main`, and the stash entry is left for
fabric-coordinator's follow-up job to drop. Measured 2026-11-01:
stash 4485e781 (29 files), head 8f317042, REPLY 01a197ce-77a2.

**Why:** the safety classifier refuses a discard of another lane's
writes, and fabric-coordinator wanted the leftovers as evidence of the
drain writing into the wrong checkout; a stash discards nothing and
unblocks the launch.

**How to apply:** never `checkout --` or `reset --hard` drain leftovers;
stash under a job-named message, fast-forward, REPLY with the stash sha
and head. Related: [[reflection-corpus-lint-drift-blocks-every-project-pr-fold-main-not-re-run]].

*References: reflection-corpus-lint-drift-blocks-every-project-pr-fold-main-not-re-run*

*Observed 2026-11-01 (architect-cto)*

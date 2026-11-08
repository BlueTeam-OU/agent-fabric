---
role: "python-dev"
class: workflow
topic: "new-job-starts-in-a-fresh-session-before-any-edit"
description: "a session that worked one job cannot commit the next; start fabric-jobs switch before editing, never `fabric-jobs start` in the old job's worktree"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - de4729e06e423070
---

## a session that worked one job cannot commit the next; start fabric-jobs switch before editing, never `fabric-jobs start` in the old job's worktree

After j92 closed I ran `fabric-jobs start j93` from the j92 worktree and built the fix in a second worktree. The commit hook then refused (ADR-037 rule 3: a session that worked a job runs the next in a fresh one), and `fabric-jobs switch j93` refused too: starting j93 there had recorded the landed j92 branch on it. `fabric-jobs project` will not re-point a job that has a branch, and `drop` cannot be undone (`add --request` then says the message "is already j93 (dropped)"). I had to save a patch, drop, and add a new job by title.

**Why:** the start recorded the cwd's branch; the work I did was lost to the session boundary, not to any code problem.
**How to apply:** when a REQUEST arrives right after a job closed, run `fabric-jobs switch` (it pauses/leaves j92, prints the `fabric-fresh --job` command) and do the reproduction in that fresh session; do not `start` it, and do no edits, in the old session.

*Observed 2026-11-04 (python-dev)*

---
role: "fabric-coordinator"
class: workflow
topic: "job-branch-via-switch"
description: "A job's branch and worktree must come from fabric-jobs switch, which records them; a worktree made by hand is not on the record and the job-copy guard denies every commit in it (j381, 2026-10-24)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 28591bf9fce64c75
---

## A job's branch and worktree must come from fabric-jobs switch, which records them; a worktree made by hand is not on the record and the job-copy guard denies every commit in it (j381, 2026-10-24)

j381 had a hand-made worktree `agent-fabric-j381` on a pushed branch, but
its record held only the main checkout as working copy and no branch or
worktree. The job-copy guard (rule 11) then refused a `git merge` in the
worktree as "outside the job's working copy", and the main checkout is on
main where nothing is committed (fleet tooling), so the job could not move.

**Why:** the guard reads the job record, not the filesystem; `choose()` in
jobsparts/branching.py records the branch and worktree only when `switch`
(or `start` through it) picks them.

**How to apply:** never `git worktree add` for a job by hand. To fix one
that was: pause the job, remove the empty hand-made worktree and branch,
`fabric-jobs switch <id>`, and run the `fabric-fresh --job` it prints.
Related: [[job-in-other-repo-needs-fresh-session]], [[resumed-subagent-loses-worktree]].

*References: job-in-other-repo-needs-fresh-session, resumed-subagent-loses-worktree*

*Observed 2026-10-24 (fabric-coordinator)*

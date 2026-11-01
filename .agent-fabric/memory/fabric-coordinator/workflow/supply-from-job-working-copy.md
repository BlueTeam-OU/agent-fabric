---
role: "fabric-coordinator"
class: workflow
topic: "supply-from-job-working-copy"
description: "making a for/ supply branch while a job is active — the one-job guard refuses a new worktree"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j381-carrier-contract-next-commit-after-363"
derived_from:
  - b751c74f4ff41b2d
---

## making a for/ supply branch while a job is active — the one-job guard refuses a new worktree

The PreToolUse one-job guard (ADR-037 rule 3) refuses a commit or cherry-pick
in any directory other than the job's own working copies, including a fresh
`git worktree add` path held in a variable. To cut a for/<caller> supply
branch from origin/main, use the job's own clean working copy:
`git switch -c <for-branch> origin/main`, cherry-pick, run the touched test
file with `fabric-python tests/<file>.py`, push, `ls-remote` to check it,
then switch back to the copy's branch. Shown on j457, 2026-10-30
(for/python-dev-02/j457-hold-accessor 3139ac97).

**Why:** a hand-made worktree is outside the job, and the guard says so
only after the attempt. [[job-branch-via-switch]]
**How to apply:** check `git status` is clean before you switch, and switch
back when you finish so the next session finds the branch it expects.

*References: job-branch-via-switch*

*Observed 2026-10-30 (fabric-coordinator)*

---
role: "python-dev"
class: workflow
topic: "blocked-bash-hook-refuses-whole-command-scratch-work-is-lost"
description: "a job-worktree guard refuses the entire Bash call, so a patch-then-cleanup chain loses the work; do the supply in the job worktree from the start"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bf98bf6ecb16aa09
---

## a job-worktree guard refuses the entire Bash call, so a patch-then-cleanup chain loses the work; do the supply in the job worktree from the start

j131: a supply test was written in a scratch worktree outside the job's working copy. The commit was refused by the one-job-worktree guard, and the whole command was refused, so the `git diff > patch` that preceded it never ran. The next call then ran `git checkout -- tests` in the scratch worktree and discarded the only copy.

**Why:** the PreToolUse guard rejects the full command, not just the commit part; nothing in a refused call executes.

**How to apply:** for a `for/user` supply, make the branch in the job's own worktree (`git checkout -b ...for/user/... origin/<pr head>`) and write there. Never discard a tree before checking that the saved copy exists. See [[supply-commit-from-job-worktree-needs-for-branch]].

*References: supply-commit-from-job-worktree-needs-for-branch*

*Observed 2026-11-15 (python-dev)*

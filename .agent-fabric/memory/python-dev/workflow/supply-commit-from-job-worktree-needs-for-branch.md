---
role: "python-dev"
class: workflow
topic: "supply-commit-from-job-worktree-needs-for-branch"
description: A supplied patch sitting in another worktree cannot be committed from there; apply it in the job worktree and switch to a for/ branch first
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 887a422a96ba865b
---

## A supplied patch sitting in another worktree cannot be committed from there; apply it in the job worktree and switch to a for/ branch first

j126 (2026-11-14): the job guard refuses `git commit` in any worktree but the job's (even via `~`/`$HOME` paths), and the commit hook refuses a supply path on a `feat/` branch. Apply the patch in the job worktree with `git apply`, `git switch -c <host>/<login>/for/user/<what>`, then commit. If the old for/ branch name is held by a stale worktree, use a suffixed name and say so in the INFO to fabric-coordinator.

**Why:** the guard resolves the commit's directory literally; a for/ branch is the only lane for supplies.
**How to apply:** `fabric-jobs deliver <id> <branch>` takes a bare branch name (no `@sha`); the job stays delivered, not done, until the fold merges. A lint plus hook suite run exceeds 120s: background it.

*Observed 2026-11-14 (python-dev)*

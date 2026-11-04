---
role: "python-dev"
class: workflow
topic: "job-worktree-by-hand-refused-use-switch"
description: "a worktree made by hand for a job is refused at commit by the job copy guard; pause the job and let fabric-jobs switch make the worktree"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66f6f55b1535540c
---

## a worktree made by hand for a job is refused at commit by the job copy guard; pause the job and let fabric-jobs switch make the worktree

A job records its working copy (and, via `switch`, its worktree). A worktree created by hand for it (`git worktree add`) is refused at commit by the job copy guard when the job names the main checkout and no worktree; the same happened to a commit in a session that had already worked a finished job (j76, j78).

**Why:** the guard binds commits to the job's own recorded copy; the fix is to make the record right, not to bypass the guard.
**How to apply:** `fabric-jobs pause <job> "<why>"`, then `fabric-jobs switch`; it resumes the paused job, creates its worktree off origin/main (a `feat/<job>-…` branch when you hold no open PR) and prints the `fabric-fresh` to run. In the fresh session copy the files over, lint, commit with a Kind trailer, run `tests/run.sh` with CI's environment, and push `HEAD:<the agreed for/ branch name>`. Do the first commit of a job in the worktree `switch` made, not in one you made yourself.

*Observed 2026-10-22 (python-dev)*

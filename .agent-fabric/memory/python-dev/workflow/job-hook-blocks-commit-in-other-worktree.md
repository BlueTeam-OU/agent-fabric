---
role: "python-dev"
class: workflow
topic: "job-hook-blocks-commit-in-other-worktree"
description: "PreToolUse hook refuses git commit in a worktree outside the job's working copy; ask the coordinator by GZCoord, never only on screen"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a81d4c1e7a49f1df
---

## PreToolUse hook refuses git commit in a worktree outside the job's working copy; ask the coordinator by GZCoord, never only on screen

A job's working copy is ~/projects/agent-fabric (ADR-037 rule 3); the hook refuses `git commit` in a sibling worktree (j159, 2026-10-24), and `fabric-jobs switch <same job>` refuses while it is active.

**Why:** the previous session left a diff uncommitted in a worktree and had already delivered it to fabric-coordinator by REPLY, who applied it (dbf68507) and said: discard the copy, do not commit a second one.

**How to apply:** on a start-up note saying "commit the worktree diff", first read whether the coordinator already applied it (`git fetch`, grep the user branch) before anything else. When blocked on a decision, send a GZCoord QUESTION to fabric-coordinator at once — the owner's rule; text on my own screen reaches nobody. Related: [[answers-trailer-marks-a-fix]].

*References: answers-trailer-marks-a-fix*

*Observed 2026-10-24 (python-dev)*

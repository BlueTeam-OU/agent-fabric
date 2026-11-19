---
role: "fabric-coordinator"
class: workflow
topic: "worktree-agents-base-on-origin-main"
description: "from a job copy beside the main checkout, a worktree-isolated subagent starts at origin/main, not the job branch — brief it so"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5dc85cc9935fbdb1
---

## from a job copy beside the main checkout, a worktree-isolated subagent starts at origin/main, not the job branch — brief it so

2026-11-16 (j830): from the job copy agent-fabric-j794-adr-064-rule-11-drills-before, four worktree-isolated subagents
were created under the MAIN checkout's .claude/worktrees/ and all started at origin/main (889138af), not at the job
branch's head (662eb34e). A brief that said "commit X is on your base" was wrong; the agent would have re-checked
survivors my branch had already killed.

**Why:** the harness makes the worktree in the main checkout, so `baseRef: head` there is not the job copy's head.
**How to apply:** before dispatching from a job copy, either brief the agent that it sees origin/main (and which of my
branch's commits it lacks), or keep the work on files the branch has not touched so its diff applies cleanly; check
with `git -C <worktree> rev-parse HEAD` after dispatch.

*Observed 2026-11-16 (fabric-coordinator)*

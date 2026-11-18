---
role: "fabric-coordinator"
class: workflow
topic: "pause-marks-session-worked"
description: "A session launched for job B that pauses the still-active job A is counted as having worked A, and job-copy-guard then refuses every commit/push for B; switch to B instead of pause+start"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b9265bd9c601fe04
---

## A session launched for job B that pauses the still-active job A is counted as having worked A, and job-copy-guard then refuses every commit/push for B; switch to B instead of pause+start

2026-11-10 (j732): a fresh session launched for j732 found j707 still active (the previous session had switched to it but never worked it) and j732 blocked on a clock. I ran `fabric-jobs pause j707` from the new session; that wrote this session's id into j707's log, so `records.session_worked` named j707, and the PreToolUse guard (`job-copy-guard.py`, rule 5) refused `git commit` for j732: "This session worked job j707, which has left active". The same session could only `fabric-jobs switch j732`, which then needed a clean copy and a memory change before it printed a fresh launch.

**Why:** ADR-037 rule 3: once a session has touched a job's state, the next job runs in a fresh session; pause counts as touching it.
**How to apply:** when a session is launched for job B and another job A is active, run `fabric-jobs switch B` first (or wait out B's clock and then switch), never `pause A` + `start B`. Draft edits made meanwhile go into a patch under the agent's state dir (`~/.local/state/agent-fabric/agents/<login>/<job>/`) so switch's clean-copy check passes. Related: [[second-job-in-session-cannot-push]], [[jobs-and-switching]].

*References: jobs-and-switching, second-job-in-session-cannot-push*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::session_worked`*

*Observed 2026-11-10 (fabric-coordinator)*

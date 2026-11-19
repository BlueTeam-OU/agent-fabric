---
role: "fabric-coordinator"
class: workflow
topic: "subagent-wait-loops-outlive-agent"
description: "A subagent's own background wait loop (until pgrep -f …; sleep) can outlive its hand-back and keep the task 'running' for hours; TaskStop <agent id> ends it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 92b029437555b407
---

## A subagent's own background wait loop (until pgrep -f …; sleep) can outlive its hand-back and keep the task 'running' for hours; TaskStop <agent id> ends it

2026-11-16 (j830): the owner saw my subagents "stuck". Four had handed back hours before, but each
still owned a background `until …; do sleep N; done` loop, so the harness kept the task running
(8-13 h). Two waited on `pgrep -f "<pattern>"` finding nothing, which never happens: the loop's own
bash command line holds the pattern. Two waited on a marker line (ALLDONE, rc= count) the run never wrote.

- The job-copy guard refuses `kill` of a process in the session's tree: `TaskStop <agent id>` stops
  the agent's task and its loops. A pipeline re-parented to `systemd --user` is outside the tree, and
  may be killed by exact pid.
- After every hand-back: `fuser` the worktree; nothing should run there. Then remove the worktree once
  its diff is committed.
- In a brief: wait with a background command's exit, never `pgrep -f` on a pattern your own command
  line carries (use `pgrep -x` or a pid file), and give every wait loop a deadline.

**Why:** a stale loop looks like a stuck agent to the owner, and holds a lock on its worktree.
**How to apply:** check `fuser` on agent worktrees whenever an agent reports done.

*Observed 2026-11-16 (fabric-coordinator)*

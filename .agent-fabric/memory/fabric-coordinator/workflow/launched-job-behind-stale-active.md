---
role: "fabric-coordinator"
class: workflow
topic: "launched-job-behind-stale-active"
description: "session launched for job B while job A was still active: pausing A marks this session as having worked a job, so fabric-pr for B is refused; send messages, block B, switch"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 357d2eb95cfd5526
---

## session launched for job B while job A was still active: pausing A marks this session as having worked a job, so fabric-pr for B is refused; send messages, block B, switch

2026-11-13, j811: the session was launched for j811 while j794 was still active. The ADR-037 rule 3 hook refused `fabric-pr arm --dry-run` in two cases:
- before the pause, because the command ran outside j794's copy;
- after `fabric-jobs pause j794` and `start j811`, because "this session worked j794", so j811 belongs to a fresh session.

`gzcoord-send` was not refused, so a DECISION carrying AUTHORIZES still went out (01a1d3ef-106a).

**How to apply:** when the launch names job B but another job is active, settle the active one first. Then do B's message-only part, block or switch, and do anything that commits or publishes (fabric-pr, push) from the fresh session that switch prints. Related: [[workflow_stale_active_job_at_launch]].

Ruling recorded in the same job: a main merge whose diff over every file of the PR is empty needs no review of its own (#573, 0b02d011).

*References: workflow_stale_active_job_at_launch*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::belongs to a fresh session`*

*Observed 2026-11-13 (fabric-coordinator)*

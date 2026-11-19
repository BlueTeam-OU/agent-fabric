---
role: "fabric-coordinator"
class: workflow
topic: "never-wait-on-owner-to-arm"
description: "Owner 2026-11-09: no agent waits on the owner to arm — it asks fabric-coordinator or architect-cto by message and takes its next job meanwhile"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ea39e46b12a36da4
---

## Owner 2026-11-09: no agent waits on the owner to arm — it asks fabric-coordinator or architect-cto by message and takes its next job meanwhile

Owner, 2026-11-09, on seeing the python-devs idle: "they should not wait me to arm but ask you or architect-cto". python-dev-01 was asking its human for the word to arm #534 with a P3 deferred. python-dev-04 stopped mid-job. python-dev-03 waited on my unanswered reply.

**Why:** a session stopped on a question to its human looks busy on the board (an active job) and does nothing. The owner is not watching panes.
**How to apply:** the arm word comes from the arming authority (`fabric-pr arm --dry-run`): me in agent-fabric, architect-cto in a project. It is asked by REQUEST, and the agent takes `fabric-jobs next` while waiting. Broadcast INFO 01a1c1dc-793e on 2026-11-09. The lasting text goes into the pull-requests skill and the Working-with-the-team section (job j718). When the owner says "idle", read the panes first (`agent-fabric-fleetdeck pane list`, harness panes, `pane read --source recent`): the board shows active jobs even when every session is stopped. Related: [[stuck-agent-read-its-pane]], [[arm-word-authorizes-line]].

*References: arm-word-authorizes-line, stuck-agent-read-its-pane*

*Observed 2026-11-09 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: workflow
topic: "iterate-fleet-queues-to-empty"
description: "Owner 2026-10-18: keep iterating on every agent's job queue, and my own, until all is done; a stuck agent gets its screen read and is unstuck"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc5b54c9f57a52b5
---

## Owner 2026-10-18: keep iterating on every agent's job queue, and my own, until all is done; a stuck agent gets its screen read and is unstuck

The owner, 2026-10-18: "keep iterating on these guys job queue till they do all their job. The same for you", and
"if you see they are stuck check their screen and unstuck them".

**Why:** the board showed most agents idle with queued or blocked work while nobody looked; queues only drain when
someone keeps cycling them.

**How to apply:** each round, read `fabric-ctl all jobs` + `fabric-ctl all presence`; an agent with queued work and no
active job, or active with no progress, gets its pane read (`agent-fabric-fleetdeck pane read <id> --source recent`)
and the cause answered: a waiting prompt answered, a safeguard stop /clear + nudge, an auto-mode refusal answered from
the pane ([[stuck-agent-read-its-pane]], [[type-into-ssh-pane]], [[safeguard-refusal-stalls-agent]]). A blocked job
whose blocker is mine is decided by me that round. Work my own queue between rounds. Count open work apart from
delivered ([[board-delivered-not-open]]).

*References: board-delivered-not-open, safeguard-refusal-stalls-agent, stuck-agent-read-its-pane, type-into-ssh-pane*

*Anchors: `tools/fabric/control/jobs.py::--stored`*

*Observed 2026-10-18 (fabric-coordinator)*

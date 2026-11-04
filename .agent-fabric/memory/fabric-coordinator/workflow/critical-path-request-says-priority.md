---
role: "fabric-coordinator"
class: workflow
topic: "critical-path-request-says-priority"
description: "A REQUEST on a PR's critical path, sent to a holder already busy, says it goes first; intake queues it behind earlier work"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a3908f8d314b0a36
---

## A REQUEST on a PR's critical path, sent to a holder already busy, says it goes first; intake queues it behind earlier work

2026-10-24, #358: I sent python-dev-01 the round-6 fix (its j159) while it
held j158, a later, non-urgent job I had given it minutes before. Intake
queued j159 behind j158, the agent worked j158, and the owner saw "that
agent is not doing it" while #358 waited on nothing else.

**Why:** a REQUEST lands as a queued job in arrival order; the holder
cannot tell which of my requests a PR is blocked on unless I say so.
**How to apply:** when a REQUEST is what an open PR waits on, say in it
"take this before your other jobs from me" (and which ones may pause);
before giving a busy holder more work, read its list and order my own
requests. If it is already queued wrong, send an INFO naming the job to
pause. Related: [[request-needs-a-job]], [[nudge-idle-agent-by-message]].

*References: nudge-idle-agent-by-message, request-needs-a-job*

*Anchors: `tools/fabric/jobs.py::queued`*

*Observed 2026-10-24 (fabric-coordinator)*

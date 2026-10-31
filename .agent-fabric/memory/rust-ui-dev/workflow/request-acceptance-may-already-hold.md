---
role: "rust-ui-dev"
class: workflow
topic: "request-acceptance-may-already-hold"
description: "A REQUEST to \"run job X\" may arrive after X closed; check X's state and the acceptance against the tool before redoing anything"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a94e3a6663e58c51
---

## A REQUEST to "run job X" may arrive after X closed; check X's state and the acceptance against the tool before redoing anything

A request naming one of my own jobs is written from the requester's view of my list,
which can be older than my last session. j154 (REQUEST 01a16fa9, "run your W43
reflection pass j137") opened 2026-10-24T20:46Z; j137 closed its fabric-reflect
cursor through row 1081 at 20:58Z the same evening, so the acceptance ("cursor closed
after j137 started; j137 done") already held when the next session took j154.

**Why:** re-running a closed pass would duplicate memories and move a cursor nobody
asked to move; the request's ACCEPTANCE line is the test, not its narrative.

**How to apply:** first `fabric-jobs show <named job>` and the tool the acceptance
reads (here `fabric-reflect status`); if it already holds, close the job with
`--no-artifact` naming the timestamps that prove it. A same-titled job queued later
(j160, owner, 2026-10-25) is a separate pass over the messages since, not a duplicate.

*Anchors: `tools/fabric/reflect.py::cmd_status`, `tools/fabric/jobs.py::--no-artifact`*

*Observed 2026-10-25 (rust-ui-dev)*

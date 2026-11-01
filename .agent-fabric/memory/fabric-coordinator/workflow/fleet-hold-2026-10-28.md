---
role: "fabric-coordinator"
class: workflow
topic: "fleet-hold-2026-10-28"
description: "LIFTED 2026-10-30 (DECISION 01a18b15-73ae). Owner 2026-10-28: orderly fleet pause — finish the active job, start or unpause none; sent as broadcast DECISION 01a182e0-647c, lifted only by a DECISION naming it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9d5727aec8eb4bfa
---

## LIFTED 2026-10-30 (DECISION 01a18b15-73ae). Owner 2026-10-28: orderly fleet pause — finish the active job, start or unpause none; sent as broadcast DECISION 01a182e0-647c, lifted only by a DECISION naming it

The owner, 2026-10-28 ~14:18Z: "orderly pause the fabric: each agent complete the current job but not start a new one or unpause one". The fabric has no hold switch: `fabric-pause` stops sessions (and only prints, exit 2, without a signal op), and `fabric-jobs switch` always starts the next job. So the instrument was a broadcast DECISION, 01a182e0-647c-772f-b90a-2dbe6a7b7da1 (seq 650799): finish the active job to its artifact, then no switch/start/unpause; a REQUEST is queued and answered "queued, held"; lifted only by a fabric-coordinator DECISION naming that id. At send: 6 active (user j403, python-dev-01 j187, python-dev-02 j98, python-dev-03 j95, python-dev-04 j72, rust-ui-dev-02 j68), 24 with none.

**Why:** a hold carried only by prose is lost by any session launched after it that misses the message; a hold the job tool enforces would not be.

**How to apply:** before lifting, read `fabric-ctl all jobs` for who is still active; lift with a DECISION citing 01a182e0. A built-in hold (switch refusing while a fleet hold is set) is worth a job. Related: [[fleet-shutdown-procedure]].

**Lifted** 2026-10-30 on the owner's word ("the HOLD decision is superseded, agents can restart their jobs"), broadcast DECISION 01a18b15-73ae-7590-9d62-aa035ca65183 (seq 654500), after the fleet was moved to andrea-benetton-blueteam-ge (claude-pzhuy-8alias-com at 100% weekly until 2026-11-02 16:00 UTC).

*References: fleet-shutdown-procedure*

*Anchors: `bin/fabric-pause`, `tools/fabric/pause.py::signal_login`*

*Observed 2026-10-28 (fabric-coordinator)*

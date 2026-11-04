---
role: "legal-expert"
class: workflow
topic: "jobs-deliver-reply-artifact"
description: "How to record a job delivered by message so fabric-jobs switch accepts it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 55a793ad4ab1e68b
---

## How to record a job delivered by message so fabric-jobs switch accepts it

A job whose deliverable is a GZCoord REPLY is recorded as `fabric-jobs deliver <job> reply:<MESSAGE-ID>`; free text naming the reply is accepted by `deliver` but refused at `switch` ("delivered needs an artifact that is open"). A wrong artifact is removed with `fabric-jobs retract <job> "<artifact exactly as recorded>"`. `switch` also refuses until the memory directory changed during the job. (Seen on j15, 2026-10-25.)

**Why:** `switch` checks the artifact's kind (PR, commit, origin branch or reply:<id>), not that something was written.

**How to apply:** deliver with `reply:<id>` from the start for every message-delivered job. See [[refused-shared-write-handoff-by-message]].

*References: refused-shared-write-handoff-by-message*

*Anchors: `tools/fabric/jobsparts/settle.py::reply:`*

*Observed 2026-10-25 (legal-expert)*

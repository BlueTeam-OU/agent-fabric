---
role: "legal-expert"
class: workflow
topic: "jobs-deliver-reply-artifact"
description: "How to record a job delivered by message so fabric-jobs switch accepts it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 55a793ad4ab1e68b
  - e6349bd81ea2b293
---

## How to record a job delivered by message so fabric-jobs switch accepts it

A job whose deliverable is a GZCoord REPLY is recorded as `fabric-jobs deliver <job> reply:<MESSAGE-ID>`; free text naming the reply is accepted by `deliver` but refused at `switch` ("delivered needs an artifact that is open"). A wrong artifact is removed with `fabric-jobs retract <job> "<artifact exactly as recorded>"`. `switch` also refuses until the memory directory changed during the job. (Seen on j15, 2026-10-25.)

`reply:<id>` must name a message with IN-REPLY-TO; a REQUEST I sent (e.g. a fold request to fabric-coordinator) is refused, so a job delivered as a pushed for/ branch is recorded as `commit:<sha> branch:<name>` (j19, 2026-11-09).

A session commits and pushes only in its own job's working copy (ADR-037 rule 3 hook): to add to an earlier job's for/ branch, branch a new for/user/<what> from its origin head in the current worktree and ask the coordinator to fold that head (j19).

**Why:** `switch` checks the artifact's kind (PR, commit, origin branch or reply:<id>), not that something was written.

**How to apply:** deliver with `reply:<id>` from the start for every message-delivered job. See [[refused-shared-write-handoff-by-message]].

*References: refused-shared-write-handoff-by-message*

*Anchors: `tools/fabric/jobsparts/settle.py::reply:`*

*Observed 2026-10-25 (legal-expert)*

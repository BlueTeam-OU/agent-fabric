---
role: "fabric-coordinator"
class: workflow
topic: "deliver-not-done-on-open-pr"
description: "job finished on a still-open PR — run `fabric-jobs deliver`, never `done`; done is terminal and switch then refuses"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e7234005a7031a80
---

## job finished on a still-open PR — run `fabric-jobs deliver`, never `done`; done is terminal and switch then refuses

On j479 (2026-10-31) I ran `fabric-jobs done j479` with its commit on the still-open #437. `done` took no evidence,
and `deliver` afterwards only appended artifacts: the state stayed done. `switch` then refused, because #437 was still
open ("delivered, not done"), and `start` refused too ("a closed job is not reopened — add a new one").
The way out: add a carrier job (j488), `start` it, `deliver` it with the PR, and give j479 a
`done --no-artifact` reason that names the carrier.

**How to apply:** when a job's artifact is a commit on an open PR, run `fabric-jobs deliver <id> <owner/repo>#N <sha>`.
Run `done` only after it merges (or let `fabric-jobs sweep` do it). Related: [[deliver-ends-publishing]].

*References: deliver-ends-publishing*

*Anchors: `tools/fabric/jobsparts/records.py::a closed job is not reopened`*

*Observed 2026-10-31 (fabric-coordinator)*

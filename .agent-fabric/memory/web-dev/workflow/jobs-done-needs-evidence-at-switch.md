---
role: "web-dev"
class: workflow
topic: "jobs-done-needs-evidence-at-switch"
description: "fabric-jobs done <id> with no artifact is accepted, but switch then refuses to leave it — record the evidence when closing, a REPLY as reply:<MESSAGE-ID>"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c8203ad12dd531ed
---

## fabric-jobs done <id> with no artifact is accepted, but switch then refuses to leave it — record the evidence when closing, a REPLY as reply:<MESSAGE-ID>

`fabric-jobs done <id>` with no artifact and no `--no-artifact` succeeds
and lists the job as done. Only the next `fabric-jobs switch` refuses
("done needs evidence it landed"), and so does a switch that names
another job. It also refuses while the memory directory is unchanged
since the job went active.

**Why:** a REQUEST answered only by a REPLY (2026-10-25, a roster row for
fabric-coordinator) looked closed, and the refusal came one step later.

**How to apply:** close a reply-only job with
`fabric-jobs deliver <id> reply:<MESSAGE-ID>`; close work that leaves
nothing to name with `done <id> --no-artifact "<what>"`. Then write the
job's memory before `switch`. To skip a paused job, name the target:
`switch <id>`. Related: [[paused-job-needs-its-branch-on-origin]].

*References: paused-job-needs-its-branch-on-origin*

*Anchors: `bin/fabric-jobs::switch`*

*Observed 2026-10-25 (web-dev)*

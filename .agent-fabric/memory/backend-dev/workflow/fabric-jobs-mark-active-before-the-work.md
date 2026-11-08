---
role: "backend-dev"
class: workflow
topic: "fabric-jobs-mark-active-before-the-work"
description: "Doing a short job (a memory fix, a reply) before running fabric-jobs to make it active — switch then refuses to leave it, because it dates \"memory changed\" from the last active stamp"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b6005fa57eef1fd2
---

## Doing a short job (a memory fix, a reply) before running fabric-jobs to make it active — switch then refuses to leave it, because it dates "memory changed" from the last active stamp

`fabric-jobs switch` will not leave a job until a memory file has changed
during it. `memory_changed` reads "during" as an mtime newer than
`started_at`, which is the job's **last `active` log stamp**. Only a job
that never went active falls back to `created`. A memory written before
the job is marked active counts as written before the job.

**Why:** j62 (2026-10-31) was a one-file memory correction. I wrote the
file at 23:04:15Z and marked j62 active, then done, at 23:04:43Z. On
2026-11-04 `switch` refused: "your memory directory has not changed during
j62", although the job's whole artifact was that memory.

**How to apply:** mark a job active before its first edit, even when the
job takes a minute. The order of operations decides whether the job's own
evidence counts.

*Anchors: `agent-fabric:tools/fabric/jobsparts/settle.py::memory_changed`, `agent-fabric:tools/fabric/jobsparts/settle.py::started_at`*

*Observed 2026-11-04 (backend-dev)*

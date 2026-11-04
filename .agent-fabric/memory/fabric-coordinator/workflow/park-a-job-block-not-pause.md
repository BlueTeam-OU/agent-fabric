---
role: "fabric-coordinator"
class: workflow
topic: "park-a-job-block-not-pause"
description: "To park a job the owner set aside, block it on \"owner: <what is awaited>\", never pause it — switch resumes a paused job first"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6699c8756cf38f83
---

## To park a job the owner set aside, block it on "owner: <what is awaited>", never pause it — switch resumes a paused job first

2026-10-20, j309: I paused it on the owner's "keep it sleeping", then `fabric-jobs switch` picked
it straight back up ("resumes paused work"). A paused job is resumed ahead of the queue. A job the
owner parks goes to `fabric-jobs block <id> "owner: <what is awaited>"`. Free text without the
`owner:` prefix (or `--on pr:|request:|job:`) is refused when the job is left.

**Why:** pause means "back to it next", not "parked".
**How to apply:** park = block on the owner, and lower its priority. Pause only work I will take
straight back.

A job waiting on a timed event (j401 on the 2026-10-30T17:00Z rollback drill) is parked the
same way: `"owner: <event> at <time>"`. `fabric-jobs start` of another job is refused while one
is active, and leaving also needs this memory directory changed during the job.

*Anchors: `tools/fabric/jobsparts/verbs.py::resumes paused work`, `tools/fabric/jobs.py::owner: <the decision awaited>`*

*Observed 2026-10-20 (fabric-coordinator)*

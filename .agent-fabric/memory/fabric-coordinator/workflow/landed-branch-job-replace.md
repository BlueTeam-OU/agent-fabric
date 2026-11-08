---
role: "fabric-coordinator"
class: workflow
topic: "landed-branch-job-replace"
description: switch refuses a job whose recorded branch a PR already landed; add a replacement job and drop the old one
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 47e73671f4ad26d8
---

## switch refuses a job whose recorded branch a PR already landed; add a replacement job and drop the old one

`fabric-jobs switch` refuses a job whose recorded branch a pull request has
landed ("it is not replaced; close … or switch to another job"), and neither
`switch` nor `start` takes a branch option. When the work is still owed, add
a new job with the same title, drop the old one with a reason that names the
new one, and `switch <new id>`. That gives it a fresh branch off origin/main.
Seen 2026-11-05: j433 had borrowed j553's branch, which landed in #485.
j433 was replaced by j622. Related: [[switch-to-named-job-directly]].

*References: switch-to-named-job-directly*

*Anchors: `tools/fabric/jobsparts/branching.py::which a pull request has landed`*

*Observed 2026-11-05 (fabric-coordinator)*

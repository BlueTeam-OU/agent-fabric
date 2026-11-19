---
role: "fabric-coordinator"
class: workflow
topic: "own-clock-block-deactivates-job"
description: "Before using fabric-jobs block on the job you are still working (to leave a note): it takes the job out of active, and the copy fence then refuses commits, pushes and fabric-pr arm until the clock passes"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a82fe54b99b270a9
---

## Before using fabric-jobs block on the job you are still working (to leave a note): it takes the job out of active, and the copy fence then refuses commits, pushes and fabric-pr arm until the clock passes

j765 (2026-11-12): I used `fabric-jobs block j765 "<progress note>" --on clock:<+1h>` as a way to write
a note while a suite ran. The job left `active`, and the PreToolUse fence then refused `fabric-pr arm`
(and would have refused the push) with "this session worked job j765, which has left active, and no job
is active". `fabric-jobs start j765` refuses while a clock has not passed, and `block --on clock:<past>`
is refused ("a time that has gone by is no wait"). The way out: re-block with a clock about 2 minutes ahead,
wait it out with a background `sleep`, then `fabric-jobs start`. The fence also judges the whole Bash line,
so `fabric-jobs start …; fabric-pr arm …` in one call is refused before start runs.

**Why:** the job state is what the copy fence reads, not what the session intends.

**How to apply:** while still working a job, keep notes out of `block` (jobs.json evidence or my memory).
Block only when handing the job off to a real wait (a request id, a PR), as the last step before the
switch. Related: [[jobs-and-switching]].

*References: jobs-and-switching*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::has left active`, `tools/fabric/jobsparts/verbs.py::a time that has gone by is no wait`*

*Observed 2026-11-12 (fabric-coordinator)*

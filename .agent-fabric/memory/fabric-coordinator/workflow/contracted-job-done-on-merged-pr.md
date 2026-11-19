---
role: "fabric-coordinator"
class: workflow
topic: "contracted-job-done-on-merged-pr"
description: "closing my job whose work a contributor's PR already merged — deliver refuses the merged PR, done refuses without evidence"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 16330a513a338efd
---

## closing my job whose work a contributor's PR already merged — deliver refuses the merged PR, done refuses without evidence

`fabric-jobs deliver <id> owner/repo#N` refuses a PR that is already merged ("the job is done, not delivered"), and `fabric-jobs done <id>` refuses a job with no delivered evidence. So a job of mine contracted to a python-dev, whose PR merged before I came back to it, cannot carry that PR as its evidence.

What worked (j720, 2026-11-10, fix was python-dev-04 j106 → BlueTeam-OU/agent-fabric#537): send the observer a REPLY naming the PR, then `fabric-jobs deliver <id> reply:<that MESSAGE-ID>` and `fabric-jobs done <id>`. The reply is landed evidence; the PR is named inside it.

**Why:** the close should still say what fixed it; `--no-artifact` loses the link.
**How to apply:** when a blocker on a contractor's job reads cleared, first verify the merged PR against the observation (a review-fix may have narrowed it: #537's 64d40290 dropped the settle.py half on purpose), then reply to whoever reported it, then deliver the reply. See [[jobs-and-switching]].

*References: jobs-and-switching*

*Anchors: `tools/fabric/jobsparts/needs.py::decide=True`*

*Observed 2026-11-10 (fabric-coordinator)*

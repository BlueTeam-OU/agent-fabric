---
role: "fabric-coordinator"
class: workflow
topic: "request-job-closes-with-the-pr-it-rode"
description: "a REQUEST job whose fix rode another job's PR stays queued; `fabric-jobs done` refuses it until it is started, so close it with start + done on the PR (j801 on #575, 2026-11-12)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bd606b3e337d3a1f
---

## a REQUEST job whose fix rode another job's PR stays queued; `fabric-jobs done` refuses it until it is started, so close it with start + done on the PR (j801 on #575, 2026-11-12)

On 2026-11-12, j801 (edge-hosting's REQUEST for the blueteam.ee deploy entry) was fixed by commit 61c39a35 on j766's PR #575, so it never became the active job. After #575 merged, `fabric-jobs done j801 <PR>` refused: "j801 is queued; done takes a job that is active or delivered". `fabric-jobs start j801` followed by `fabric-jobs done j801 BlueTeam-OU/agent-fabric#575` closed it, and `switch` then asked for a memory change for j801 too.

This is also the cost the owner named that day: an unrelated REQUEST riding another topic's PR waits on that PR's whole review. Here edge-hosting's j38 waited hours on #575. See [[next-work-rides-the-open-pr]] for the same-topic narrowing (j807).

**Why:** a job closed out of order still owes its evidence and its memory change before switch lets the session go.
**How to apply:** after a PR merges, close every job its commits answered with start then done on the PR, and tell the sender (a REPLY naming the merge commit).

*References: next-work-rides-the-open-pr*

*Anchors: `tools/fabric/jobs.py::the active or delivered job`*

*Observed 2026-11-12 (fabric-coordinator)*

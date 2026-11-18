---
role: "fabric-coordinator"
class: workflow
topic: "assign-dont-preverify"
description: "before sending a job to an idle contributor, do not have a subagent (or myself) verify its claims in the code first; that verification is the assignee's work"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 497540f993026a01
---

## before sending a job to an idle contributor, do not have a subagent (or myself) verify its claims in the code first; that verification is the assignee's work

On 2026-11-14 the four python devs were idle. Before sending them j848, j850, j863 and j866, I started an Explore subagent to check each job's claims against origin/main. The owner said this makes no sense: verifying and diagnosing is the job itself, and the assignee does it, with their own subagents if they want.

**Why:** pre-verifying holds idle agents waiting on me and does their work twice. My job is the contract and the dispatch, not the diagnosis.

**How to apply:** when contributors are idle, send REQUESTs straight away. Each one carries the job's facts as reported, the source message ids, the acceptance criteria and what is out of scope, and says "verify against origin/main first". I check only routing: which entry the files fall in and the never-list. Related: [[delegate-to-subagents]], [[iterate-fleet-queues-to-empty]].

**Queue more than one job.** The owner, on the same day: give each idle contributor a next job too, marked "queue this after <job>", so they never go idle between jobs. On 2026-11-14 each python dev got two: pd-01 j241 then j691; pd-02 j149 (j863) then j830's test-speed pass; pd-03 j836 then j849 Q5; pd-04 j123 (j866) then j867's P3. Block my own job on each request with `fabric-jobs block <j> --on-request <id>`.

*References: delegate-to-subagents, iterate-fleet-queues-to-empty*

*Anchors: `policies/authority.json::contributors`*

*Observed 2026-11-14 (fabric-coordinator)*

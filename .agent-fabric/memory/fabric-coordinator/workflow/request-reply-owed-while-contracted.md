---
role: "fabric-coordinator"
class: workflow
topic: "request-reply-owed-while-contracted"
description: "a REQUEST I turn into a contract for a contributor still owes its sender a REPLY at once; check gzcoord-sent.jsonl for the mid"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - aa4c49cfd7768eb6
---

## a REQUEST I turn into a contract for a contributor still owes its sender a REPLY at once; check gzcoord-sent.jsonl for the mid

j754 (2026-11-13): language-culture-ge's REQUEST 01a1c6ea (2026-11-10) became my job, contracted to python-dev-04 (REQUEST 01a1c9d2,
their j108, landed as BlueTeam-OU/agent-fabric#556 on 11-11). The sender got no REPLY for three days: the job sat "blocked on
job:python-dev-04/j108" and the reply was left for the close. The sender meanwhile queued its own job to chase it (gzapi.ge j753).

**Why:** a REQUEST's sender waits on the reply, not on the fix; silence costs them a follow-up job.
**How to apply:** when I contract a REQUEST out, REPLY to its sender that day naming the contract (request id, holder, job). Before
closing a job that came from a REQUEST, check it was answered:
`grep -c <mid-prefix> ~/.local/state/agent-fabric/agents/<login>/gzcoord-sent.jsonl` (0 = never answered). The job's
`source` may read `self` when I added it by hand, so the job record alone does not show a REQUEST is owed.
Related: [[gzcoord-messaging]], [[jobs-and-switching]].

*References: gzcoord-messaging, jobs-and-switching*

*Anchors: `tools/fabric/jobsparts/needs.py::no branch: no working copy needed`*

*Observed 2026-11-13 (fabric-coordinator)*

---
role: "legal-expert"
class: workflow
topic: "jobs-question-blocker-never-clears"
description: "fabric-jobs block --on request:<id> where <id> is a QUESTION: the answer never clears it, and the job cannot be restarted"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d706f6dd51638e0c
---

## fabric-jobs block --on request:<id> where <id> is a QUESTION: the answer never clears it, and the job cannot be restarted

On 2026-11-10 j20 was blocked on `request:<id>` of a QUESTION to legal-expert-ch. ch answered by REPLY, but `fabric-jobs start j20` refused it: the blocker read "unknown (answered, but whether it became a job is not known: refused: job-state answers the sender of the request the job was taken from)". `tools/fabric/jobsparts/blockers.py` `_became`: the peer refuses the job-state ask and the reply names no job, so the blocker reads unknown, never cleared. The commit hook then refuses commits, because no job is active. Reported to fabric-coordinator as OBSERVATION 01a1c6f5-67e7-7684-96e2-e940012fd46f.

**Why:** a QUESTION never becomes a job on the answerer's board, so the request: blocker form, built for REQUESTs, cannot tell its answer.

**How to apply:** until fabric-coordinator answers, do not block a job on a QUESTION's id. Commit and push what the job has first, then wait with the job active, or block it on a clock: blocker.

*Observed 2026-11-10 (legal-expert)*

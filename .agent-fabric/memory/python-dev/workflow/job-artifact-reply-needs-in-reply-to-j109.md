---
role: "python-dev"
class: workflow
topic: "job-artifact-reply-needs-in-reply-to-j109"
description: "fabric-jobs deliver reply:<id> only accepts a message sent with IN-REPLY-TO; a plain INFO id is refused at switch; arm-only jobs deliver with pr: alone"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 925ec2327a1b0cb5
---

## fabric-jobs deliver reply:<id> only accepts a message sent with IN-REPLY-TO; a plain INFO id is refused at switch; arm-only jobs deliver with pr: alone

j109 (arm #459 on the owner's word, then tell fabric-coordinator) was delivered with `pr:459 reply:<INFO id>`; `fabric-jobs switch` then refused: the INFO named no answer this login sent, because it carries no IN-REPLY-TO. Fix was `fabric-jobs retract j109 reply:<id>`; `pr:` alone is the artifact.
**Why:** a job whose message is an announcement (INFO) has no request to answer, so the reply artifact does not apply; switch also wants a memory change during the job.
**How to apply:** for "arm, then tell the coordinator" jobs, deliver with `pr:<N>` only. Arming under 8 work commits worked with `--basis "the owner's word, relayed by fabric-coordinator per job jN: arm N; counts, head, review, threads"` (#459 merged at once).

*Observed 2026-11-04 (python-dev)*

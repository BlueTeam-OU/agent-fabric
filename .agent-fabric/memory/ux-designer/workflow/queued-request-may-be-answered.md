---
role: "ux-designer"
class: workflow
topic: "queued-request-may-be-answered"
description: before working a queued REQUEST job, read its thread — an earlier session may have answered it when it arrived
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c87d62d5dd8f32bf
---

## before working a queued REQUEST job, read its thread — an earlier session may have answered it when it arrived

A REQUEST is queued as a job on delivery, but the session that was running then may answer it at once (a phone-order stop, a lease release) without ever starting the job. j102 (REQUEST 01a1bb25, 2026-11-08) reached its turn two days later with REPLY 01a1bb26 and INFO 01a1bb2d already sent, so the only work left was closing it.

**Why:** working it again would mean a duplicate REPLY, and acting on a phone order that has expired (e.g. re-taking a lease that was already handed back).

**How to apply:** first step on any request job: `fabric-history --thread <message-id> --full`. If the acceptance is already met, re-check the live state it claimed (here `fabric-lease --who pixel-9a`), close the job with `--no-artifact` naming the sent messages, and move any leftover step to the job that owns it (here j101, the phone order's 3b). Related: [[check-spec-before-answering]].

*References: check-spec-before-answering*

*Anchors: `tools/fabric/history.py::--thread`, `tools/fabric/jobs.py::--no-artifact`*

*Observed 2026-11-10 (ux-designer)*

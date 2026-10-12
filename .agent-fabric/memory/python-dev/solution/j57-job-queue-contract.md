---
role: "python-dev"
class: solution
topic: "j57-job-queue-contract"
description: "the job queue (ADR-037 rules 7-10) — merged in #118, what was carried, where its parts live"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9fac11d993a1497d
  - e5869d02c6c4dff1
---

## the job queue (ADR-037 rules 7-10) — merged in #118, what was carried, where its parts live

Merged 2026-10-08 in agent-fabric #118 (e01dd720, 8 work, 6 fix), with new-agent --human.
Parts: tools/fabric/jobs.py (priority, prio, block --on-request, list --stored, pool-list,
pool-claim, next's offer); tools/fabric/control/queue.py (waits from the
state stream, the ask of the holder on the control channel); tools/fabric/control/pool.py
(holder: config pool_holder, else the single host's operator, else refuse); tools/fabric/control/sessions.py waits_on.
Carried, named in #118's body: with node unable to start, pool-claim says "may be claimed" though
nothing was sent (fix: sent=False in ask_queue's OSError branch); waitsFrom has no freshness bound;
roleFromStream reads only 500 records; gzcoord.mjs api() has no fetch timeout. Not verified: a live
holder over the real relay.

Corrected 2026-10-11: the Node control plane was deleted in a20b4159 and these parts are Python now. The carries that name the Node (node unable to start, gzcoord.mjs api() without a fetch timeout) refer to code that no longer exists; waitsFrom without a freshness bound and roleFromStream's 500 records were not re-checked.

*Observed 2026-10-11 (python-dev)*

---
role: "fabric-coordinator"
class: threads
topic: "fabric-op-ssh-unexercised"
description: "bin/fabric-op landed (#418, ADR-029 rule 19) but its real ssh backend and a non-self --as were never exercised; live check due when the second host runs"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 40de1148f5e4dc1c
---

## bin/fabric-op landed (#418, ADR-029 rule 19) but its real ssh backend and a non-self --as were never exercised; live check due when the second host runs

`bin/fabric-op` (break-glass action path, `tools/fabric/control/breakglass.py`) merged 2026-10-30 in #418; its ADR text in #422 (ADR-029 rule 19, ADR-003 ledger flock), the cross-process busy lock in #423/#426. Tests ran hostexec's local backend only: the real ssh backend and `--as <other login>` (sudo) are untested, per #418's Limits. When the second host runs (j422 milestone, same trigger as [[j422-owner-answers-q1-q7]] and j440), do a live read-back of `fabric-ctl <login> <op> --via hostexec` to that host and record it under `docs/live-checks/`. Until then, do not call fabric-op proven as a remote break-glass path.

*References: j422-owner-answers-q1-q7*

*Observed 2026-10-30 (fabric-coordinator)*

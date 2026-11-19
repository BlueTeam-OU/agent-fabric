---
role: "fabric-coordinator"
class: solution
topic: "control-dual-fleet-rollout"
description: "2026-11-13: control_carrier dual reached the fleet (#583, b036baac); what the first all-ping on dual showed, and the restart burst to expect"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8fc19ba241c27928
---

## 2026-11-13: control_carrier dual reached the fleet (#583, b036baac); what the first all-ping on dual showed, and the restart burst to expect

#583 merged on 2026-11-13. `fabric-ctl all upgrade fabric` took 29 accounts to b036baac; python-dev-01 was already current. That put `control_carrier` on `dual` fleet-wide (ADR-029 rule 18).

Before the switch, every profile was re-rendered with the `fabric-control` endpoint (`fabric-ctl all interweave-start`: 27 re-rendered, 3 already).

The first `fabric-ctl all ping` on dual:
- 30 ok, 29 of them answered by InterWeave.
- `relay only: user`: the operator's own account is not carried, a #571 limit.
- The 29-target run through one interweave-human child did not wedge.

Expect a burst during the restart. In the operator's control-arrivals.jsonl, 32 agentd `no-waiter` InterWeave replies arrived in one second (07:37:52). They belonged to 3 earlier requests (gateway ×29, identity ×2, upgrade ×1), and their relay copies had already been served. This is the rollout-window effect the #583 review predicted. It appeared once and then stopped.

Tests: every suite that drives ctl in-process pins `FABRIC_CONTROL_CARRIER`, and `tests/run.py` pins it too. See [[committed-default-flip-reaches-suites]].

*References: committed-default-flip-reaches-suites*

*Observed 2026-11-13 (fabric-coordinator)*

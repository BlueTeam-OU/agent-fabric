---
role: "fabric-coordinator"
class: solution
topic: "own-row-loopback-618"
description: "fabric-ctl's own-account row no longer needs the relay; how to read it back"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 077f488ce0c859d9
---

## fabric-ctl's own-account row no longer needs the relay; how to read it back

Since #618 (merged 2026-11-15, python-dev-01 j245) agentd loops a request to its own address back
in-process (`control_link.Carrier._loop_request`); `reply` routes it to the waiter. Read-back: the
operator's `control-arrivals.jsonl`, kind=reply from `<host>/<own login>`, carrier `interweave` verdict
`ok` from 2026-11-15T00:07:08Z (371 by 11-16). The relay copy keeps arriving beside it under `dual`.
Not exercised: RELAY_ONLY_OPS (still relay/fabric-op) and the relay-stopped case (gate 2). Plan
W18 and the §2.5 row, on #624 (j871). Related: [[control-dual-fleet-rollout]].

*References: control-dual-fleet-rollout*

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::_loop_request`*

*Observed 2026-11-16 (fabric-coordinator)*

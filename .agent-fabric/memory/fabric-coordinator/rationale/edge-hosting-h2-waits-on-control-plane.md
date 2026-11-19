---
role: "fabric-coordinator"
class: rationale
topic: "edge-hosting-h2-waits-on-control-plane"
description: "owner 2026-11-13: edge-hosting cannot move to fabric-h2 until the control plane is on InterWeave; gates j27 and H2 P3"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b4071a58c176f88a
---

## owner 2026-11-13: edge-hosting cannot move to fabric-h2 until the control plane is on InterWeave; gates j27 and H2 P3

The owner, in the coordinator's session on 2026-11-13, said: "till control plan is on interweave also is impossible to move edge-hosting to fabric-h2".

What this gates:
- Placing edge-hosting on fabric-h2 (H2 P3, [[h2-owner-answers-2026-11-11]]).
- edge-hosting's j27 (QUESTION 01a1d3e1-d028).

What counts as done: every fabric:control path to h2 runs over InterWeave, operator included. As of #583 (2026-11-13) the operator is relay-only ([[control-dual-fleet-rollout]]). The SSH fallback ([[control-plane-remote-fallback-and-public-peer]]) is break-glass, not the control plane.

This also needs the public port: [[d9-public-port-fabric-h2]].

**How to apply:** do not say "ready" to edge-hosting, and do not change edge-hosting's placement in runtime/hosts/registry.json, before the cross-host control plane is read back live. The parity report is necessary but not enough.

*References: control-dual-fleet-rollout, control-plane-remote-fallback-and-public-peer, d9-public-port-fabric-h2, h2-owner-answers-2026-11-11*

*Observed 2026-11-13 (fabric-coordinator)*

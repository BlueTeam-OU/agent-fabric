---
role: "fabric-coordinator"
class: threads
topic: "j598-overlaps-499"
description: "j598 (watch reads the carrier only after a relay fetch succeeds) is likely done by python-dev-03's #499; check before working it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dd2ab909b9d8e634
---

## j598 (watch reads the carrier only after a relay fetch succeeds) is likely done by python-dev-03's #499; check before working it

j598's defect (watch.py read iw.unseen() only after a successful relay fetch, so a carrier-only message
never reached a session during a relay outage) is what BlueTeam-OU/agent-fabric#499 (python-dev-03, j115,
merged 2026-11-07) fixed: a failed fetch with the carrier present stands for an empty page; tests in
tests/test_gzcoord_carrier_inbox.py cover shown once, survives a restart, not shown again when the relay returns.
Paused 2026-11-07 for j632 on the owner's word. Next: read #499's tests against j598's three proofs
(reaches the session, survives restart, appears once); if all three hold, close j598 citing #499.

*Observed 2026-11-07 (fabric-coordinator)*

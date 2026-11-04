---
role: "fabric-coordinator"
class: workflow
topic: "owner-runs-project-arms"
description: "Who arms a project PR under its minimum or on its boundary is what fabric-pr arm --dry-run names from the records; the owner's 2026-10-19 decision moved it off the owner"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 22bfd27075f57761
  - 575b27a1fceac07d
---

## Who arms a project PR under its minimum or on its boundary is what fabric-pr arm --dry-run names from the records; the owner's 2026-10-19 decision moved it off the owner

2026-10-19, the owner: "architect-cto must be able to arm and merge on gzapp and interweave, agents should ask
him not me to do so" — replacing the rule of 2026-10-14, under which every project PR below its minimum was
the owner's hand. The same day the owner gave fabric-coordinator the arms of agent-fabric, agent-fabric-gateway
and agent-fabric-fleetdeck, boundary changes included; the own-PR refusal is a policy setting
(`commits.authority_own_prs`).

**Why:** the owner should not be the arming bottleneck for project work.

**How to apply:** never answer "who arms" from memory. Run `fabric-pr arm <n> --dry-run` and name the authority
it prints, which it reads from `policies/arming.json` and the client's settings repository; those records are
the only authority ([[repo-ownership-from-records]]). Related: [[owner-arm-only-when-verified]],
[[repo-transfer-owner-hand]].

*References: owner-arm-only-when-verified, repo-ownership-from-records, repo-transfer-owner-hand*

*Anchors: `tools/fabric/github/arm.py::the owner's word`, `tools/fabric/github/arm_policy.py::boundary_authority`*

*Observed 2026-10-23 (fabric-coordinator)*

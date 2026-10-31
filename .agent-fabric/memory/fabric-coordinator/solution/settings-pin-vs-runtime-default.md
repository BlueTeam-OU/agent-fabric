---
role: "fabric-coordinator"
class: solution
topic: "settings-pin-vs-runtime-default"
description: "Removing an override from agent-fabric-settings hands the repo the fleet default of whatever agent-fabric checkout arms it, not the validate pin's; check the fleet's version before merging"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9b0afd2c7a0c1f43
  - ca4113054cb7e889
---

## Removing an override from agent-fabric-settings hands the repo the fleet default of whatever agent-fabric checkout arms it, not the validate pin's; check the fleet's version before merging

A `repos/<repo>.json` in an organisation's agent-fabric-settings is merged by `arm_policy.load` over
`fleet_policy(root)` of the agent-fabric checkout running the arm (the code default with that checkout's
`policies/arming.json` over it). The settings repository's own validate workflow pins `AGENT_FABRIC_REF`, and
that only decides which agent-fabric commit validates the files (both settings repositories, read 2026-10-23).
So deleting an override (2026-10-15, both settings repos' #6: the claude-only `reviews`/`boundary_reviews`
stopgap of #5) is safe only once every arming account runs a fabric whose default says the same;
`fabric-ctl all status` (the fabric column) answers it.

Bump the pin in the same PR, or validate judges the files against an old default.

**Why:** both blind reviews of the #6 PRs raised this risk independently. An account still on a fabric from
before #264 would have made codex blocking again everywhere.
**How to apply:** before merging any settings change that relies on a new fleet default, check the fabric
column in `fabric-ctl all status`; distribute first (`fabric-ctl all upgrade fabric`) if any account is behind.
Who arms a settings PR is what `fabric-pr arm --dry-run` prints. Related: [[codex-additional-never-blocking]].

*References: codex-additional-never-blocking*

*Anchors: `tools/fabric/github/arm_policy.py::def fleet_policy`, `tools/fabric/github/arm_policy.py::def load`, `settings-blueteam:.github/workflows/validate.yml::AGENT_FABRIC_REF`, `settings-gzapi:.github/workflows/validate.yml::AGENT_FABRIC_REF`*

*Observed 2026-10-23 (fabric-coordinator)*

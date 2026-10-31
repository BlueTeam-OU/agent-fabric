---
role: "fabric-coordinator"
class: solution
topic: "settings-pin-vs-runtime-default"
description: "Removing an override from agent-fabric-settings hands the repo the fleet default of whatever agent-fabric checkout arms it, not the validate pin's; check the fleet's version before merging"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ca4113054cb7e889
---

## Removing an override from agent-fabric-settings hands the repo the fleet default of whatever agent-fabric checkout arms it, not the validate pin's; check the fleet's version before merging

A repos/<repo>.json in an organisation's agent-fabric-settings is merged by `arm_policy.load`
over `fleet_policy(root)` of the agent-fabric checkout running the arm. The settings repo's
`AGENT_FABRIC_REF` in `.github/workflows/validate.yml` only decides which agent-fabric commit
validates the files. So deleting an override (2026-10-15, both settings repos' #6: the
claude-only `reviews`/`boundary_reviews` stopgap of #5) is safe only once every arming account
runs a fabric whose default says the same; `fabric-ctl all status` (the fabric column) answers it.

Bump the pin in the same PR, or validate judges the files against an old default. Both
settings repos count every changed file as a security boundary, so a two-commit PR there is
armed on the owner's word.

**Why:** both blind reviews of the #6 PRs raised this risk independently. An account still on a
fabric from before #264 would have made codex blocking again everywhere.
**How to apply:** before merging any settings change that relies on a new fleet default, check
the fabric column in `fabric-ctl all status`; distribute first (`fabric-ctl all upgrade fabric`)
if any account is behind. Related: [[codex-additional-never-blocking]].

*References: codex-additional-never-blocking*

*Anchors: `tools/fabric/github/arm_policy.py::def fleet_policy`, `tools/fabric/github/arm_policy.py::def load`*

*Observed 2026-10-15 (fabric-coordinator)*

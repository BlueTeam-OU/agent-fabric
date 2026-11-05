---
role: "devex-tooling"
class: solution
topic: "appless-required-context-reads-other"
description: "A required status context with no App (fabric/armed) comes back from rules/branches with no integration_id; any \"every check is Actions'\" test must leave it out"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 218c93c2814fedb1
---

## A required status context with no App (fabric/armed) comes back from rules/branches with no integration_id; any "every check is Actions'" test must leave it out

`gh api repos/<r>/rules/branches/main` on agent-fabric reads (2026-11-02)
`[{"context":"ci-ok","integration_id":15368},{"context":"fabric/armed"}]`: arm_policy.render() requires the
arming's status with no App, because fabric-pr arm posts it with a session's token. wait_merged's
required_checks_configured counted it as another App's check, so the missing-run stall never fired on an auto
repository. j272 (04c3bab4, for/user/j272-armed-status-p3s) filters arm_policy.ARMED_STATUS out first.

**Why:** anything that classifies required contexts by integration_id must also handle the App-less arming
context, or it fails on every auto repository.
**How to apply:** when code reads a ruleset's required contexts, check the live answer for the App-less entry
and filter on arm_policy.ARMED_STATUS (one name, fixed; see [[arm-authorization-beside-owner-word]]).

*References: arm-authorization-beside-owner-word*

*Anchors: `tools/fabric/github/wait_merged.py::required_checks_configured`, `tools/fabric/github/arm_policy.py::ARMED_STATUS`*

*Observed 2026-11-02 (devex-tooling)*

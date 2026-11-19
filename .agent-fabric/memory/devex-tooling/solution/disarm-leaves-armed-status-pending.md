---
role: "devex-tooling"
class: solution
topic: "disarm-leaves-armed-status-pending"
description: "fabric-pr disarm sets fabric/armed to pending (GitHub deletes no status); pr-gate's checks_of leaves that context out, else re-arm waits on it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e2140d3979b5ecca
---

## fabric-pr disarm sets fabric/armed to pending (GitHub deletes no status); pr-gate's checks_of leaves that context out, else re-arm waits on it

`fabric-pr disarm` (tools/fabric/github/disarm.py, j310, branch
develop-qzapp/devex-tooling/for/user/fabric-pr-disarm, commits 3ecb67d1 + 60f311ec)
cannot delete the head's fabric/armed success, so it posts the same context at pending.
In an auto repository the ruleset then holds the head until it is armed again.

pr_gate.checks_of drops the arm_policy.ARMED_STATUS context from the rollup. Otherwise
that pending status reads as "pending:1", and arm's gate 6 refuses to re-arm the head on
a repository with no required check. Dropping it also closes a loophole: arm's own success
used to make a head with no CI read "green" when it was armed again.

**Why:** a status the tool writes about itself is not a check of the code.
**How to apply:** a new status context the fabric posts (not CI) goes into checks_of's
exclusion as well. Who may disarm is who may arm: the PR's own session, or
--any-owner with the owner's word or "<authority>'s word" for the policy's
below_min_authority/boundary_authority, checked against the session's binding.
Related: [[appless-required-context-reads-other]]

*References: appless-required-context-reads-other*

*Anchors: `tools/fabric/github/pr_gate.py::arm_policy.ARMED_STATUS`, `tools/fabric/github/disarm.py::DISARMED_DESCRIPTION`*

*Observed 2026-11-09 (devex-tooling)*

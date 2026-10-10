---
role: "fabric-coordinator"
class: workflow
topic: "coordinate-dont-build"
description: Before writing code in the fabric, check whose entry it is — the owner wants me coordinating, designing and delegating, not developing scripts
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d3a899738a689898
---

## Before writing code in the fabric, check whose entry it is — the owner wants me coordinating, designing and delegating, not developing scripts

With three python-devs and devex-tooling as contributors, work inside a contributor's entry (policies/authority.json) goes to its holder as a REQUEST with the contract; my own code is the never-list (CONTRIBUTOR_NEVER + excluding) and what no holder can take in time, said so in the commit. My job is design (records, plans, the map of the projects around the fabric), dispatch, review, distribution.

**Why:** the owner, 2026-10-08, while I was writing fabric-watch myself: "your role is really more coordination and less script developing", "and also more designing/overview of agent-fabric and related projects". Charter changed in 6559f9fd (develop-qzapp/user/feat/deck-activation).

**How to apply:** before Write/Edit under tools/, runtime/, tests/, bin/: is the path in a contributor entry and not on the never-list? Then write the REQUEST instead; hand any draft over on a for/<holder> branch. Read `fabric-ctl all jobs` to pick the least-loaded holder; tell the owner when the fleet needs another login. See [[delegate-to-python-dev]], [[delegate-check-never-list]].

*References: delegate-check-never-list, delegate-to-python-dev*

*Observed 2026-10-08 (fabric-coordinator)*

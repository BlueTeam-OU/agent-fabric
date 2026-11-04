---
role: "devex-tooling"
class: solution
topic: "role-minimum-typed-trailer"
description: "commits.roles in an arming policy lowers the minimum by the Fabric-Role trailer, which any committer can type; what that implies and how a brand-comms grant was built"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5cbfd06df983e2bc
---

## commits.roles in an arming policy lowers the minimum by the Fabric-Role trailer, which any committer can type; what that implies and how a brand-comms grant was built

`commits.roles: {"<role>": {"min": N}}` in a settings repository's repos/<repo>.json gives a PR a lower work-commit minimum when every non-merge commit carries the same `Fabric-Role:` trailer. arm.py `author_role` reads that trailer from the message text only. policies/githooks/commit-msg adds the bound role only when no trailer is present, and checks a typed trailer against the binding only for guarded (.agent-fabric/) changes. So any committer can claim the role. Both blind reviews of the brand-comms grant found this (BlueTeam settings #8 F2, gzapi settings #7 §3, 2026-10-19); the fix is to check against the author login's bound role (queued as its own job).

`threshold` gives a security-boundary change max(min, boundary_min) before it looks at roles, so a role minimum never lowers a boundary PR. That needs the project's arm.json, which is fabric-coordinator's.

Moving a repository off `owner-only` widens arming for every role, not only the one the change is meant for. Say so in the file's description.

The owner's grant (2026-10-19): brand-comms arms its own PRs, with no one's permission, in blueteam.brand, blueteam.ee, gzapi.brand, gzapi.ge and gzapp.decks. The owner chose to remove the boundary entirely (asked of fabric-coordinator, REQUEST 01a152a4) and to make blueteam.brand `direct`.

*Anchors: `tools/fabric/github/arm.py::def author_role`, `tools/fabric/github/arm_policy.py::def threshold`*

*Observed 2026-10-19 (devex-tooling)*

---
role: "devex-tooling"
class: solution
topic: "role-minimum-typed-trailer"
description: "commits.roles lowers fabric-pr arm's minimum by the Fabric-Role trailer, which anyone can type; since 466623e5 arm takes it only when presence binds the branch's login to that role"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 570c8efcbd01e9a3
  - 5cbfd06df983e2bc
---

## commits.roles in an arming policy lowers the minimum by the Fabric-Role trailer, which any committer can type; what that implies and how a brand-comms grant was built

`commits.roles: {"<role>": {"min": N}}` in a settings repository's repos/<repo>.json gives a PR a lower work-commit minimum when every non-merge commit carries the same `Fabric-Role:` trailer. arm.py `author_role` reads that trailer from the message text only. policies/githooks/commit-msg adds the bound role only when no trailer is present, and checks a typed trailer against the binding only for guarded (.agent-fabric/) changes. So any committer can claim the role. Both blind reviews of the brand-comms grant found this (BlueTeam settings #8 F2, gzapi settings #7 §3, 2026-10-19); the fix is to check against the author login's bound role (queued as its own job).

`threshold` gives a security-boundary change max(min, boundary_min) before it looks at roles, so a role minimum never lowers a boundary PR. That needs the project's arm.json, which is fabric-coordinator's.

Moving a repository off `owner-only` widens arming for every role, not only the one the change is meant for. Say so in the file's description.

The owner's grant (2026-10-19): brand-comms arms its own PRs, with no one's permission, in blueteam.brand, blueteam.ee, gzapi.brand, gzapi.ge and gzapp.decks. The owner chose to remove the boundary entirely (asked of fabric-coordinator, REQUEST 01a152a4) and to make blueteam.brand `direct`.

*Anchors: `tools/fabric/github/arm.py::def author_role`, `tools/fabric/github/arm_policy.py::def threshold`*

*Observed 2026-10-19 (devex-tooling)*

## commits.roles lowers fabric-pr arm's minimum by the Fabric-Role trailer, which anyone can type; since 466623e5 arm takes it only when presence binds the branch's login to that role

`commits.roles: {"<role>": {"min": N}}` in a settings repository's repos/<repo>.json gives a PR a lower
work-commit minimum when every non-merge commit carries the same `Fabric-Role:` trailer. arm.py `author_role`
reads that trailer from the message text; policies/githooks/commit-msg adds the bound role only when no trailer
is present and checks a typed one against the binding only for guarded `.agent-fabric/` changes, so on its own
any committer could claim the role. Both blind reviews of the brand-comms grant found it
(BlueTeam-OU/agent-fabric-settings#8 F2, gzapi-org/agent-fabric-settings#7 §3, 2026-10-19).

The fix, j157 (466623e5, on main; supplier review F1 fixed in 2a09e6ac): `role_bound` takes a trailer role
that would lower the floor only when fabric-ctl presence of the branch's `<host>/<login>` reports that role.
Another role, no role or an unnamed branch falls back to the repository's minimum, and the log says why; a host
mismatch falls back too, said. If presence cannot answer, Unanswered (exit 2). Presence is asked only when
`threshold(role) != threshold(None)`. `presence_of(login)` returns presence's (host, role); `held_role` wraps it
for `verify_grant` (waiver and authorization), where a host mismatch is still exit 2 ("presence places <login>
on <host>"). Branch names are typed too, so this stops a mistake, not a forger.

`threshold` gives a security-boundary change max(min, boundary_min) before it looks at roles, so a role minimum
never lowers a boundary PR; the boundary is the project's arm.json, fabric-coordinator's. Moving a repository off
`owner-only` widens arming for every role, not only the intended one: say so in the file's description.

In test_arm_policy, a run_arm that gives a role a lower minimum needs `presence=presence_of(role=…, login="me")`
(the default branch is h/me/feat/x); a branch that is not this session's needs `--any-owner`. The grant itself:
[[brand-comms-arming-grant]].

*References: brand-comms-arming-grant*

*Anchors: `tools/fabric/github/arm.py::def role_bound`, `tools/fabric/github/arm.py::def presence_of`, `tools/fabric/github/arm.py::def author_role`, `tools/fabric/github/arm_policy.py::def threshold`*

*Observed 2026-11-01 (devex-tooling)*

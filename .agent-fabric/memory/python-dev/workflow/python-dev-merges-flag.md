---
role: "python-dev"
class: workflow
topic: "python-dev-merges-flag"
description: "once develop-qzapp/user/feat/python-dev-merges is on main, python-dev opens its own PRs in agent-fabric (ADR-018 merges flag)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5196d69873dd7cc0
  - 9f70cfb2a8bcd6da
---

## since #109 python-dev opens its own PRs in agent-fabric (ADR-018 merges flag), reviews them and arms them at the arming policy's gate

2026-10-07, fabric-coordinator (REPLY 01a116c6, seq 16932): branch
develop-qzapp/user/feat/python-dev-merges sets "merges": true on
python-dev's contributors entry in policies/authority.json (ADR-018).
MERGED as #109 (f0b4bb1a, INFO 01a116f2 seq 17126): now my work goes on
develop-qzapp/<login>/<type>/<what>, one open PR of mine, my own blind
review posted with fabric-pr post-review, fabric-pr gate read before
arming; arming follows the repository's policy (owner, 2026-10-11: commits.min 1 on agent-fabric, so at the review gate with the basis posted; a security-boundary change under 8 needs the owner's word or architect-cto's AUTHORIZES line). Paths outside my entry: ask the coordinator to put them on
my branch. Tell the coordinator when a PR merges (it distributes). A
for/user branch never opens a PR (CI refuses).
j50 was folded there (2c64f44d); version check before step 5 declined.

Corrected 2026-10-11: the shell shims are gone (fabric-pr verbs) and the 8-commit rule is the arming policy's, per repository.

*Observed 2026-10-11 (python-dev)*

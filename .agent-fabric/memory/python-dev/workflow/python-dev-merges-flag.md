---
role: "python-dev"
class: workflow
topic: "python-dev-merges-flag"
description: "once develop-qzapp/user/feat/python-dev-merges is on main, python-dev opens its own PRs in agent-fabric (ADR-018 merges flag)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5196d69873dd7cc0
---

## once develop-qzapp/user/feat/python-dev-merges is on main, python-dev opens its own PRs in agent-fabric (ADR-018 merges flag)

2026-10-07, fabric-coordinator (REPLY 01a116c6, seq 16932): branch
develop-qzapp/user/feat/python-dev-merges sets "merges": true on
python-dev's contributors entry in policies/authority.json (ADR-018).
MERGED as #109 (f0b4bb1a, INFO 01a116f2 seq 17126): now my work goes on
develop-qzapp/<login>/<type>/<what>, one open PR of mine, my own blind
review posted with runtime/github/post-review.sh, pr-gate.sh read before
arming; >=8 work commits and MERGEABLE: arm myself with the basis, fewer:
ask the owner. Paths outside my entry: ask the coordinator to put them on
my branch. Tell the coordinator when a PR merges (it distributes). A
for/user branch never opens a PR (CI refuses).
j50 was folded there (2c64f44d); version check before step 5 declined.

*Observed 2026-10-07 (python-dev)*

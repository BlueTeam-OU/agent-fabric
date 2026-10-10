---
role: "fabric-coordinator"
class: workflow
topic: "delegate-check-never-list"
description: "Before assigning fabric work to a contributor, check the paths against CONTRIBUTOR_NEVER and its entry's excluding list"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0bbaedcdc83e858c
---

## Before assigning fabric work to a contributor, check the paths against CONTRIBUTOR_NEVER and its entry's excluding list

On 2026-10-07 I assigned python-dev-01 the lint.py decomposition. tools/fabric/lint.py is on CONTRIBUTOR_NEVER (lint.py:1796), so I had to withdraw it twice (seq 13772, 13781). A first crossed reply proposed moving the rules into contributor-writable modules (tools/fabric/lint_rules/), which would have put the fence's rules outside the fence.

**Why:** lint holds every contributor entry to its list. A split that lets a contributor own the rule modules weakens the guard it implements.

**How to apply:** before a REQUEST to python-dev-01 or devex-tooling, grep the target paths against `CONTRIBUTOR_NEVER` and `policies/authority.json` `excluding`. Anything under the fence stays mine, and its refactors too. See [[delegate-to-python-dev]].

*References: delegate-to-python-dev*

*Observed 2026-10-06 (fabric-coordinator)*

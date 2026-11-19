---
role: "fabric-coordinator"
class: workflow
topic: "authority-path-needs-file-on-main"
description: "A contributor's new file needs an authority.json entry: it can ride neither the contributor's PR (charter_authority judges the branch owner) nor mine before the file exists (lint: path not in the tree); add it after their merge"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8341305a2ef975ef
---

## A contributor's new file needs an authority.json entry: it can ride neither the contributor's PR (charter_authority judges the branch owner) nor mine before the file exists (lint: path not in the tree); add it after their merge

2026-11-16 (#630, j911): a python-dev moved mocks into a new tests/arm_mocks.py that devex-tooling must also edit.
- My commit adding the path on python-dev-04's branch went red: check_charter_authority refuses policies/authority.json
  on any branch not owned by fabric-coordinator, whatever the commit's Fabric-Role.
- On my own PR the lint refuses it: "path 'tests/arm_mocks.py' is not in the tree".
- Rewriting the contributor's branch to drop my commit was refused by auto mode; the branch's owner resets it.

**Why:** both fences are right; the order is the only way through.
**How to apply:** when a contributor's change creates a file another role edits, let it merge, then add the path on my
next PR (a job blocked on pr:<their PR>); the reviewer's finding on their PR closes by --defer naming that job.

*Observed 2026-11-16 (fabric-coordinator)*

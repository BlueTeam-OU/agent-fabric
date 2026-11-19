---
role: "fabric-coordinator"
class: solution
topic: "blueteam-brand-arm-no-ci"
description: "How fabric-pr arm treats BlueTeam-OU/blueteam.brand — a direct repository with no CI, where the owner's no-CI word is not read"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: blueteam.brand
    working_copy: blueteam.brand
derived_from:
  - 6845d938af38ccd1
---

## How fabric-pr arm treats BlueTeam-OU/blueteam.brand — a direct repository with no CI, where the owner's no-CI word is not read

BlueTeam-OU/blueteam.brand is a *direct* repository to `fabric-pr arm`: with no check on the
head it merges on the review of its head alone, and the dry-run says "the owner's no-CI word is
not needed here: it is not read" — so the basis carries only the count word ("the owner's word
…"), and adding a no-CI clause would post it verbatim to no effect. Arm merges immediately
(`gh pr merge --merge --match-head-commit`). Shown arming #4 at e60dc707 on 2026-11-14 (1 work,
2 fix, minimum 8, merged as ebe14db9). Advisory there: the repo still allows squash and rebase
merges, which the arming policy wants off — a settings change for the owner.

*Observed 2026-11-14 (fabric-coordinator)*

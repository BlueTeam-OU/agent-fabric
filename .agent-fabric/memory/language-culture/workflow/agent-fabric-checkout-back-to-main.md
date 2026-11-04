---
role: "language-culture"
class: workflow
topic: "agent-fabric-checkout-back-to-main"
description: "After pushing a for/ supply in agent-fabric, return your checkout to main — fabric-ctl all upgrade skips a checkout sitting on a branch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8727bd1dc632c627
---

## After pushing a for/ supply in agent-fabric, return your checkout to main — fabric-ctl all upgrade skips a checkout sitting on a branch

After supplying and pushing a `for/` branch from your agent-fabric working copy, switch the checkout back to `main` (`git switch main`). `fabric-ctl all upgrade fabric` skips an account whose working copy is not on main: on j89 (2026-10-24) the fleet upgrade (#368, 72689ab8) refused my account exactly because the checkout still sat on `for/python-dev-02/j89-carrier-keys-ru` (db2bebdf), clean and pushed — nothing was lost, but the upgrade did not run. The holder rule, in the owner's words: a supply is made and pushed from a worktree, or the checkout goes back to main once pushed. After the push, switch to main (the branch stays on origin for the receiving agent to fold) and REPLY that the checkout is on main so the coordinator reruns the upgrade.

*Anchors: `bin/fabric-ctl::upgrade`*

*Observed 2026-10-25 (language-culture)*

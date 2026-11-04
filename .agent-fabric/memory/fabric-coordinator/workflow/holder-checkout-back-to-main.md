---
role: "fabric-coordinator"
class: workflow
topic: "holder-checkout-back-to-main"
description: "After I fold a contributor's or locale holder's branch that its own agent-fabric checkout is on, tell it to switch back to main (or work in a worktree): fabric-ctl all upgrade never moves a checkout off a branch, so that account is skipped"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a976880d0ce2d36
---

## After I fold a contributor's or locale holder's branch that its own agent-fabric checkout is on, tell it to switch back to main (or work in a worktree): fabric-ctl all upgrade never moves a checkout off a branch, so that account is skipped

Locale holders and contributors kept their agent-fabric clone on the supply branch after I folded it. The fleet upgrade then skipped them and they ran merges behind ("distributed to every account but language-culture-ge"; "three merges behind until you do").

**Why:** the upgrade never moves a checkout off a branch; the account keeps old fabric code silently.
**How to apply:** in the fold or merge message, ask the holder to return its checkout to main; after `fabric-ctl all upgrade fabric`, read the fabric column of `fabric-ctl all status` for any login left behind. Related: [[own-checkout-is-fleet-tooling]], [[own-account-upgrade]].

*References: own-account-upgrade, own-checkout-is-fleet-tooling*

*Observed 2026-10-22 (fabric-coordinator)*

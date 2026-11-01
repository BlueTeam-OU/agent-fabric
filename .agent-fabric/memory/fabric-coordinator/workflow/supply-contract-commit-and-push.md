---
role: "fabric-coordinator"
class: workflow
topic: "supply-contract-commit-and-push"
description: "A supply request states the whole delivery contract: commit AND push the for/ branch, no review of its own, which self-checks its REPLY carries; before folding or naming a head, read it back with git ls-remote and merge-base --is-ancestor"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 75174f65f6309d22
---

## A supply request states the whole delivery contract: commit AND push the for/ branch, no review of its own, which self-checks its REPLY carries; before folding or naming a head, read it back with git ls-remote and merge-base --is-ancestor

Four suppliers in one day handed back a for/ branch that was "not on origin" because my request said "commit" and not "push". Elsewhere I named a head whose fold had conflicted, accepted a base that did not contain an already folded commit, and a script sent a reply after its commit failed. The owner added on 2026-10-22 that a supplier dispatches no review of its own part; my requests had not said so.

**Why:** a missing term in the request becomes a round trip per supplier, and an unverified sha becomes a wrong fold.
**How to apply:** every supply REQUEST says commit and push, no own review, and the checks the REPLY reports. Before a fold, `git ls-remote origin <branch>`; before naming a base or head, `git merge-base --is-ancestor` for every folded commit. Related: [[fold-then-ci-then-review-then-arm]].

*References: fold-then-ci-then-review-then-arm*

*Observed 2026-10-22 (fabric-coordinator)*

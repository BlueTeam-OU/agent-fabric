---
role: "fabric-coordinator"
class: workflow
topic: "brief-invariant-merges-declare-nothing"
description: "a review brief's trailer invariant must say \"every non-merge commit\" — else each fold's merge comes back as a Kind finding"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bea30b5af099c894
---

## a review brief's trailer invariant must say "every non-merge commit" — else each fold's merge comes back as a Kind finding

#511 (j674, 2026-11-08): my review requests said "Every commit carries Kind and Fabric-Role trailers". The review class
then raised the unrebased fold merges (9b66f49c, 297c924b) as findings in two rounds (F21, F23), although AGENTS.md
and ADR-019 §5 rule 3 say a merge declares nothing.

**Why:** the reviewer judges against the brief's words, not the repository's rule; a wrong invariant manufactures a
finding every round and costs a judgement each time.
**How to apply:** in `fabric-review brief` requests write "Every non-merge commit carries Kind and Fabric-Role
trailers; contributed commits keep their own Fabric-Role". A fold merged before its out-of-entry patch is also
unbisectable: note it in the PR body at fold time, before a reviewer finds it. Related: [[review-and-guards]].

*References: review-and-guards*

*Observed 2026-11-08 (fabric-coordinator)*

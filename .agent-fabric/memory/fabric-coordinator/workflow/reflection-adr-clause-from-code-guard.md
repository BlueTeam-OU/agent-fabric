---
role: "fabric-coordinator"
class: workflow
topic: "reflection-adr-clause-from-code-guard"
description: "An ADR or DIGEST clause I supply for someone's code drifts in scope, condition or quantity; write each clause from the code path's guard conditions, naming the line that makes it true, never from the requester's summary"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d21cd8f0086814d9
---

## An ADR or DIGEST clause I supply for someone's code drifts in scope, condition or quantity; write each clause from the code path's guard conditions, naming the line that makes it true, never from the requester's summary

In W44 the implementers' re-reviews corrected the ADR text I had written for their PRs more often than any other single thing. The errors came in three kinds. Scope: "one request per page and per account" was not what the code did. Condition: a rule said a case is "refused" when the code refuses it only when the copy is dirty, and a start row overstated when its reservation applies. Quantity: budget seconds were stale. Two DIGEST trims also dropped words that lookups use. And a negative claim in an amendment note ("no caller") came from a grep limited to one directory, and the tree refuted it.

**Why:** I write the clause from the REQUEST and the requester's summary, and the code's guards are narrower than either.
**How to apply:** for each clause, open the code path and name the condition that makes it true (`if dirty and …`). State "refused when X" with X exactly as the code tests it. Check a negative claim with an unscoped `git grep` over the whole tree. Read numbers back by import ([[budget-prose-read-back-by-import]]). Check DIGEST words with [[digest-trim-keeps-lookups]]. Write the text after the last code-changing round, and re-read it each round after that.

*References: budget-prose-read-back-by-import, digest-trim-keeps-lookups*

*Observed 2026-11-01 (fabric-coordinator)*

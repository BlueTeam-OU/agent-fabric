---
role: "python-dev"
class: domain
topic: "status-sentinel-collides-with-read-state"
description: deriving an outcome string from a remote state (state.lower()) and testing it against a success sentinel — the read value can BE the sentinel
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 162901a225893e1b
---

## deriving an outcome string from a remote state (state.lower()) and testing it against a success sentinel — the read value can BE the sentinel

A success decided by `if outcome == "merged"`, where another branch sets `outcome = state.lower()`
from a remote answer, passes whenever the remote says MERGED by any path — the head check bypassed.
Found by mutation (deleting the head-checked branch left the test green) in agent-fabric #121's
arm.py read-back, before review.

**Why:** a value read from outside and a verdict the code reached share one namespace; the read
value impersonates the verdict.

**How to apply:** keep the verdict a separate boolean (`merged = state == "MERGED" and head == pinned`)
and give read states a prefix in messages (`f"state {state}"`); plant the mutation "drop the
verdict branch" — it must fail a test. Related: [[review-before-suite-and-numeric-guards]].

*References: review-before-suite-and-numeric-guards*

*Observed 2026-10-08 (python-dev)*

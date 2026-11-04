---
role: "python-dev"
class: workflow
topic: "arm-pins-head-ask-who-rides-first"
description: "arming uses --match-head-commit, so commits the requester planned to push onto the PR miss it; ask before arming (j76, #439)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ba25bd7d8ae7e04c
---

## arming uses --match-head-commit, so commits the requester planned to push onto the PR miss it; ask before arming (j76, #439)

A request that says "tell me the PR number so my commits ride it" means the
requester will push onto the branch. `fabric-pr arm` merges with
`--match-head-commit <head>`, so anything pushed after arming does not ride.
In j76 the coordinator's ADR and skill commits turned out to go on their own PR
(#437), but I could not know that without asking.

**Why:** an armed head is final; a later push disarms or is left out.

**How to apply:** after the review is clean and before `fabric-pr arm`, send one
QUESTION: "pushed yet, or arm now?" and wait for the REPLY. Arm with that
REPLY's id in the basis. Here the count minimum was 1, so a single work commit
armed at the review gate (`fabric-pr arm --dry-run --basis x` prints the rule).
Also: `strftime("%Y")` does not zero-pad years below 1000 on glibc builds;
format a stored date with `f"{d.year:04d}"` when the result is parsed back.

*Observed 2026-10-31 (python-dev)*

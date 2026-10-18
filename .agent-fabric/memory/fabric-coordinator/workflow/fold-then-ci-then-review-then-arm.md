---
role: "fabric-coordinator"
class: workflow
topic: "fold-then-ci-then-review-then-arm"
description: "Owner 2026-10-13: a caller folds every supplied commit back BEFORE review and the full CI run; order is fold → tests/run.sh (full) → blind review → arm, and a new supply restarts it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c50d6350a2d2debd
---

## Owner 2026-10-13: a caller folds every supplied commit back BEFORE review and the full CI run; order is fold → tests/run.sh (full) → blind review → arm, and a new supply restarts it

The owner, 2026-10-13, after #242 was reviewed and armed and THEN needed devex-tooling's test fix
folded in (the arm stalled on platform-smoke): "the process must be more precise. if someone
dispatch a work (commit) to another agent, it have to fold in back before doing review and the full
ci run".

**Why:** a review or CI run of a head that is not the final one is wasted, and arming it invites
exactly tonight's stall; contributors' changes break tests the caller did not think to run.
**How to apply:** for any PR with supplied work: (1) fold every supplied commit or branch; an
outstanding supply means not ready — no review, no arm; (2) run the full tests/run.sh on the folded
tree; (3) one blind review of that head; (4) arm the same head. Any new supply restarts at (1).
Ask the same of every caller. To write into identities/prompt's team section ("A change has one
owner…") in the next PR. Related: [[fold-then-full-suite]], [[owner-arm-only-when-verified]].

*References: fold-then-full-suite, owner-arm-only-when-verified*

*Observed 2026-10-13 (fabric-coordinator)*

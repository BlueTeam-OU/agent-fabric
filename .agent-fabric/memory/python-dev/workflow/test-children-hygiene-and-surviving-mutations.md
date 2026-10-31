---
role: "python-dev"
class: workflow
topic: "test-children-hygiene-and-surviving-mutations"
description: "review-finding classes on Python tests — child interpreters write __pycache__ into the checkout, shared-temp escape targets, fixtures that make the named mutation survive"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1e7cf6ec2a965c5b
---

## review-finding classes on Python tests — child interpreters write __pycache__ into the checkout, shared-temp escape targets, fixtures that make the named mutation survive

Three reviewers' findings on my test hunks fell in the same classes, twice each; check them before delivering a test, not after the review.
- A test child that imports repo modules writes `__pycache__` into the checkout: set `PYTHONDONTWRITEBYTECODE=1` in the child's rebuilt env (every test that spawns a Python child, not only the one reviewed).
- A "nothing escaped" test must use a unique name (uuid) with `addCleanup`, never a fixed file in the shared temp dir: an unrelated file fails it and a regressed guard leaves residue. A guard that creates before it checks (`makedirs` before the realpath test) is itself the defect the test must pin; keep a positive control that writes inside.
- A fixture can make the named mutation unreachable (a setUp that commits before branching turned a "both sides moved" merge into an ancestor fold, so replacing the merge-tree call by MERGE_HEAD's tree survived). Run the mutation against the OLD fixture too and show it stays green, then against the fixed one and show it fails; name the mutation in the docstring.
- Every branch of a helper (timeout, final existence check, probe location, start-probe exit code) needs its own mutation; a probe that runs `/bin/true` passes a sandbox that ran nothing, so give it a distinctive exit code.
**Why:** #230 and #231 each came back with these findings after a first review called the tests done.
**How to apply:** before delivery, list each branch of the code touched, plant one mutation per branch from a script that copies the file aside, runs, restores.

*Observed 2026-10-18 (python-dev)*

---
role: "python-dev"
class: workflow
topic: "merge-another-sessions-pr-post-review-lane-guard"
description: "'merge N' on a PR of another login: arm --any-owner works, post-review does not; the owner's session posts the claude review; codex is not required"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9efd8e7851be26f6
---

## 'merge N' on a PR of another login: arm --any-owner works, post-review does not; the owner's session posts the claude review; codex is not required

j85 / #444 (2026-11-01): the owner's "merge 444" lifts the work-commit count and `arm --any-owner` lifts the ownership
check, but `fabric-pr post-review` has no override (tools/fabric/github/post_review.py lane guard) and `arm` refuses
until a claude review of the *current* head is posted. My blind review (Finding: none) could not be posted.
**Why:** the guard stops posting on a branch of another login; the head also moved twice (coordinator re-assembled the drain), so a review of the old head would not have counted anyway.
**How to apply:** before reviewing someone else's PR for a merge job, send the owner's session a REQUEST to post its own review (it did, as its own job); do not review early on a head that is still moving; poll `fabric-pr gate N` for "claude ✓" and green checks, then `arm N --any-owner --basis`. "codex absent" is information only (policies/arming.json additional_reviews). A huge memory-drain diff: brief with range merge-base..PR-head, scripts over the tree, not a merge of main (the brief pins the head sha it is given).

*Anchors: `tools/fabric/github/post_review.py::belongs to`*

*Observed 2026-11-01 (python-dev)*

---
role: "fabric-coordinator"
class: workflow
topic: "post-review-own-pr-only"
description: "fabric-pr post-review refuses another session's PR: a review I dispatch on a contributor's PR goes as a PR comment, and the author's own re-review is the counted one"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 63ca0d67da7a078e
---

## fabric-pr post-review refuses another session's PR: a review I dispatch on a contributor's PR goes as a PR comment, and the author's own re-review is the counted one

2026-10-18, #299 (python-dev-02's): I dispatched the review class on its head and `fabric-pr post-review 299` refused
— "belongs to develop-qzapp/python-dev-02 … Not posting. That session is mid-flight on work you cannot see, and a
review cannot be unsent. Raise it in the PR instead." I posted the report with `gh pr comment` and asked the author to
run and post its own review after the fix.

**Why:** the gate counts only reviews posted by the PR's own session; a comment is the record, not the review.

**How to apply:** on another session's PR, don't dispatch a review to be counted; ask the author for it, or comment a
review I ran as input. Related: [[owner-arm-only-when-verified]].

*References: owner-arm-only-when-verified*

*Anchors: `tools/fabric/github/post_review.py::belongs to`*

*Observed 2026-10-18 (fabric-coordinator)*

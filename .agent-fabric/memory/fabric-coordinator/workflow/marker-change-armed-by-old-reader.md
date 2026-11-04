---
role: "fabric-coordinator"
class: workflow
topic: "marker-change-armed-by-old-reader"
description: "A PR that changes the review marker or the gate's reader is armed by main's tools, never its own; post the final review through main's post-review too"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95d38b8577f4dd8d
---

## A PR that changes the review marker or the gate's reader is armed by main's tools, never its own; post the final review through main's post-review too

#358 (ADR-065) moved post-review to a v2 marker and taught the readers v2;
main's installed `fabric-pr gate`/arm only read v1. The branch's own
`bin/fabric-pr gate` showed `claude ✓ codex ✓` while main's showed `✗`.

Arming with the branch's own gate code would be the PR certifying itself
through the gate it changes. So the final review is posted twice: through
the branch's `bin/fabric-pr post-review` (v2, the record and checkpoint)
and through main's `fabric-pr post-review` (v1, what main's arm counts).
Only PRs after the merge rely on the new reader.

**Why:** the gate and arm are a security boundary (projects/agent-fabric/
integration/gh/arm.json); a change to them is judged by the code already
on main.
**How to apply:** for any PR touching post_review, pr_review_status,
review_status/, results.py or arm*, check `fabric-pr gate` from PATH, not
the worktree's, before arming; if they disagree, post the final review
with main's tools as well. Related: [[arm-after-checks-not-during]],
[[owner-arm-only-when-verified]].

*References: arm-after-checks-not-during, owner-arm-only-when-verified*

*Anchors: `tools/fabric/github/post_review.py::REVIEW_MARKER`, `tools/fabric/github/review_status/config.py::REVIEW_MARKER`*

*Observed 2026-10-24 (fabric-coordinator)*

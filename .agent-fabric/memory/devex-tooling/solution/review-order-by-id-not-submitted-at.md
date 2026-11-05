---
role: "devex-tooling"
class: solution
topic: "review-order-by-id-not-submitted-at"
description: Ordering GitHub PR reviews to find the last one — use the review id, never submitted_at (GitHub served it in the future)
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8a4de07f9e43bbd2
---

## Ordering GitHub PR reviews to find the last one — use the review id, never submitted_at (GitHub served it in the future)

GitHub returned submitted_at out of posting order for 2 of agent-fabric-fleetdeck#57's reviews (they read as future at
the time). The review chain now orders by `review_status.base.review_order`, which uses the review id first and the
time only for rows without an id (j270, branch develop-qzapp/devex-tooling/for/user/j270-review-chain-future-submitted-at,
62ec2bbb). The callers are review_checkpoint (fabric-pr next / the re-review base), arm_findings (gate 4c) and the
review-status display. A review fabric-pr posts is one POST with event COMMENT, so the id is its submission order. A
person's pending-then-submitted review keeps the id from when it was begun, which only the display reads.

**Why:** an order GitHub can skew picks the wrong last review, and with it the wrong checkpoint or a finding left open.

**How to apply:** where a decision rests on the order, a review without an int id (bool excluded) is a doubt: the
checkpoint gives None and gate 4c reports it unknown. A test fixture of reviews needs ids. To keep a case's ordering
and same-time ties as written, take the id from the timestamp's digits (test_post_review_cli, test_review_rounds).
Comparing a review time with a comment time (probe.py's refusal currency) is not fixed by ids: review and comment
ids are two sequences. j283 (9223ff41, for/user/j283-trial-merge-descendants) sets aside a review dated after the
probe's read, so it supersedes no refusal; a skewed date already in the past is still undetectable. Gate 4c names a
no-id review by its marker's head (32fbb61d). See [[one-format-one-parser]].

*References: one-format-one-parser*

*Anchors: `tools/fabric/github/review_status/base.py::review_order`, `tools/fabric/github/review_checkpoint.py::review_id`*

*Observed 2026-11-04 (devex-tooling)*

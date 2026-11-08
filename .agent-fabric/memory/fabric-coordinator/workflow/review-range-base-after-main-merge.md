---
role: "fabric-coordinator"
class: workflow
topic: "review-range-base-after-main-merge"
description: "a review request's range base is the PR's merge-base with main computed after the last main merge — a stale base makes post-review refuse the whole round"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8e305fe26ac801ee
---

## a review request's range base is the PR's merge-base with main computed after the last main merge — a stale base makes post-review refuse the whole round

2026-11-05, #488 round 1 (j618): I wrote `range: c59e63e7..1e98d952` by hand, with c59e63e7 copied from an
earlier merge-base (python-dev-01's #491 branch). I had merged origin/main into #488 minutes before, so its
merge-base was fd10a755. The review ran for 22 minutes, and `fabric-pr post-review 488` then refused it:
"base c59e63e7 is neither the merge-base fd10a755 of PR #488 with main … nor the head of the PR's last
checkpoint review". The findings were still real, and I fixed them, but the round could not be posted.

**Why:** post-review counts only a full range (merge-base..head) or a re-review from the last posted head. A
wider range is not the PR's review.
**How to apply:** fill `range:` from `git merge-base origin/main HEAD` right after the last `git fetch` and
merge, never from an earlier note. Related: [[review-request-fields]], [[review-report-from-handback]].

*References: review-report-from-handback, review-request-fields*

*Anchors: `tools/fabric/github/post_review.py::neither the merge-base`*

*Observed 2026-11-05 (fabric-coordinator)*

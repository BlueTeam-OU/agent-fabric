---
role: "web-dev"
class: workflow
topic: "ci-red-fixed-on-main-needs-a-fold"
description: "A PR's check is red for a cause outside its diff and the fix is on main — a re-run will not turn it green; fold origin/main, push, re-arm"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a50c1b22484fb89
---

## A PR's check is red for a cause outside its diff and the fix is on main — a re-run will not turn it green; fold origin/main, push, re-arm

When a PR's check goes red for a reason outside its diff (a runner image
change, a test that breaks on a date), and the fix has landed on the
default branch, the PR stays red: each run uses the PR branch's own copy
of the test and the workflow, and re-running the old job runs that same
copy again. A merge-queue eviction with the same failure has the same
cause.

**Why:** two gzapp broadcasts, both 2026-10-25 and from different roles,
gave the same remedy: ban-checks red after the runner moved to a new
image, and status_web's time-zone test red in merge_group once summer
time ended.

**How to apply:** first confirm the failure matches the announced cause.
Then run `git merge --no-ff origin/main` on the PR branch (not a rebase)
and push. The push takes auto-merge off (agent-fabric ADR-019 §5 rule 5,
disarm-on-push), so re-arm with `fabric-pr arm` once the checks pass. If
the fix has not landed yet, a queued PR will just be evicted again, so
wait for the fix to merge before you fold.

*Anchors: `.github/workflows/disarm-on-push.yml::auto-merge`*

*Observed 2026-10-25 (web-dev)*

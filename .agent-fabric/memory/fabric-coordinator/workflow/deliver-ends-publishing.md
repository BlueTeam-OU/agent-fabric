---
role: "fabric-coordinator"
class: workflow
topic: "deliver-ends-publishing"
description: "fabric-jobs deliver takes the job out of active, and the one-job Bash guard then refuses every publishing command (fabric-pr arm, even --dry-run, post-review); deliver after the review and the arm, or re-activate with fabric-jobs start…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35fd2bc535b1b9a8
---

## fabric-jobs deliver takes the job out of active, and the one-job Bash guard then refuses every publishing command (fabric-pr arm, even --dry-run, post-review); deliver after the review and the arm, or re-activate with fabric-jobs start (j381, 2026-10-24)

On 2026-10-24 (j381, PR #371) I ran `fabric-jobs deliver` as soon as the PR
was open, then `fabric-pr arm 371 --dry-run` was refused: "This session worked
job j381, which has left active, and no job is active. This command commits or
publishes". `fabric-jobs start j381` re-activated the delivered job and the
session went on.

**Why:** ADR-037 rule 3: once a session has worked a job, the next job runs in
a fresh session; the guard reads "no active job" as "between jobs". The
agent-jobs skill's "its artifact exists → deliver" is read too early if the
PR still needs its review, post-review and arm from this session.

**How to apply:** open the PR, run the suite, review, post, arm, then deliver;
if delivered early, `fabric-jobs start <id>` and go on. See
[[job-branch-via-switch]], [[fold-then-ci-then-review-then-arm]].

*References: fold-then-ci-then-review-then-arm, job-branch-via-switch*

*Observed 2026-10-24 (fabric-coordinator)*

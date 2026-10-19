---
role: "backend-dev"
class: domain
topic: "actions-rerun-keeps-old-workflow"
description: "A PR check fails on CI configuration that main has since fixed — a re-run will not pick up the fix; update the branch from main"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 785999cf641eae44
---

## A PR check fails on CI configuration that main has since fixed — a re-run will not pick up the fix; update the branch from main

Re-running a failed GitHub Actions job replays that run's original workflow snapshot
(the workflow files at the run's commit). A fix to the workflow, or to anything the job
checks out at the run's ref, that landed on main afterwards is not seen. The job fails
again the same way. A fresh run on a new head is needed: `gh pr update-branch <n>`, or
merge origin/main into the branch and push.

**Why:** gzapp 2026-09-14. ban-checks went red on every PR after a token-requiring
checkout step was replaced on main (#699). Re-running the failed jobs on #697/#698
failed again at the old "control plane is reachable" step. Updating both branches from
main turned them green. Ruled by fabric-coordinator in 01a09fe3-3d55.

**How to apply:** when a CI-blocking fix lands on main and your PR is red for that
reason, update the branch from main, then expect green. Don't re-run, and don't wait
for the queue to do it.

*Observed 2026-10-15 (backend-dev)*

---
role: "flutter-dev"
class: workflow
topic: "red-check-fixed-on-main-needs-push"
description: "A PR check red for a cause already fixed on main does not go green on a re-run; fold origin/main (--no-ff) and push, then re-arm"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4c510ee8560a4ee9
---

## A PR check red for a cause already fixed on main does not go green on a re-run; fold origin/main (--no-ff) and push, then re-arm

### A PR check that is red for a cause already fixed on main does not go green on a re-run: fold origin/main (`git merge --no-ff origin/main`), push, then re-arm.

A pull_request run tests the merge ref computed when that run's event
fired (gzapp `.github/workflows/_ban-checks.yml`, checkout comment:
"on a pull_request checks out the MERGE ref"). Re-running the old job
reuses that merge ref, so it still lacks the fix on main. A new push
gives a new merge ref; the fold is that push, made explicitly, and it
needs no change to your diff.

Every push takes auto-merge off an armed PR (agent-fabric ADR-019 §5
rule 5, `disarm-on-push.yml`), so arm the PR again after the fold. If
the fix is still on an open PR, it is not on main yet: a queued PR is
evicted again until that PR lands, so wait for it before folding.

Seen twice in 2026-W43 on gzapp. ban-checks went red when the
ubuntu-latest runner image changed. A status_web zone test failed in
merge_group when summer time ended. Both owners' broadcasts said the
same thing: fold, push, re-arm. Not checked: whether a push without a
fold also recomputes the merge ref in every workflow; the fold is the
form both owners gave.

*Anchors: `gzapp:.github/workflows/_ban-checks.yml::on a pull_request checks out the MERGE ref`, `.github/workflows/disarm-on-push.yml`*

*Observed 2026-10-26 (flutter-dev)*

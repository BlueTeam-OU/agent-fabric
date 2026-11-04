---
role: "devex-tooling"
class: domain
topic: "gh-rerun-keeps-workflow-snapshot"
description: "re-running a failed GitHub Actions job replays the run's old workflow file; after a workflow fix on main, a PR needs a fresh run (update the branch), not a re-run; a guard workflow the PR must not disable runs on pull_request_target"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 51aa018bdb240472
  - 79f7dae215ec69cb
---

## re-running a failed GitHub Actions job replays the run's old workflow file; after a workflow fix on main, a PR needs a fresh run (update the branch), not a re-run; a guard workflow the PR must not disable runs on pull_request_target

A re-run of a failed GitHub Actions job keeps the workflow snapshot of the run it repeats. When the
fix is in the workflow itself (gzapp #699 dropped a dead token from the agent-fabric checkout in
ban-checks, 2026-09-14), "Re-run failed jobs" on an open PR fails again at the same step. The PR
needs a new run on the new workflow: `gh pr update-branch <n>` or a fold of origin/main.

The same rule applies to new runs. A `pull_request` run uses the workflow files on the PR's own
branch, so a branch cut before a workflow change keeps running the old workflow until it folds
main. The #854 timeouts and the blame-hang flag reached a branch only through a fold (2026-09-18).
That also works the other way: merging an unlanded workflow branch into yours gives your PR's run
that instrument (the blame-hang flag) before it reaches main. Say in the PR body which range is
folded.

The flip side, for a workflow that guards the PR it runs on: `pull_request: synchronize` runs the
PR's own merge-ref copy. A push that edits, deletes or breaks the guard therefore runs that copy,
or nothing. agent-fabric's disarm-on-push.yml had this hole. gzapp #1135's port uses
`pull_request_target` (types: [synchronize]), which runs the base branch's copy. It checks out
nothing and runs no PR code, and event data reaches the script only through env.

The same holds for any check script in the tree, not only the workflow. A PR runs its own
branch's copy of the test the job calls. When gzapp ban-checks went red on every PR from the
runner image (2026-10-24, [[ubuntu-2604-runner-uutils-coreutils]]), the fix on main reached a PR
only through a fold. A push of the fold also disarms an armed PR, so the broadcast has to say
"fold, push, re-arm".

**How to apply:** after landing a fix to a CI workflow or to a check script it runs, tell every open branch to update from main, not
to re-run; when a re-run still fails on a step main has fixed, check which workflow sha the run used
before debugging the PR.

*References: ubuntu-2604-runner-uutils-coreutils*

*Observed 2026-10-22 (devex-tooling)*

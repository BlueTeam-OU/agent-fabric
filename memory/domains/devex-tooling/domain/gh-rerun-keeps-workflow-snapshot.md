---
role: "devex-tooling"
class: domain
topic: "gh-rerun-keeps-workflow-snapshot"
description: "re-running a failed GitHub Actions job replays the run's old workflow file; after a workflow fix on main, a PR needs a fresh run (update the branch), not a re-run"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 51aa018bdb240472
---

## re-running a failed GitHub Actions job replays the run's old workflow file; after a workflow fix on main, a PR needs a fresh run (update the branch), not a re-run

A re-run of a failed GitHub Actions job keeps the workflow snapshot of the run it repeats. When the
fix is in the workflow itself (gzapp #699 dropped a dead token from the agent-fabric checkout in
ban-checks, 2026-09-14), "Re-run failed jobs" on an open PR fails again at the same step. The PR
needs a new run on the new workflow: `gh pr update-branch <n>` or a fold of origin/main.

**How to apply:** after landing a CI-workflow fix, tell every open branch to update from main, not
to re-run; when a re-run still fails on a step main has fixed, check which workflow sha the run used
before debugging the PR.

*Observed 2026-10-16 (devex-tooling)*

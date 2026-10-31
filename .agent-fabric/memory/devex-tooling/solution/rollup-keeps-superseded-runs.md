---
role: "devex-tooling"
class: solution
topic: "rollup-keeps-superseded-runs"
description: "statusCheckRollup.contexts lists every check run on a head, cancelled/re-run ones too; read the latest per check"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4f118be3cba8be3c
---

## statusCheckRollup.contexts lists every check run on a head, cancelled/re-run ones too; read the latest per check

A PR's `statusCheckRollup { contexts }` lists every check run on the head, including runs of a workflow run that a reopen cancelled or a re-run replaced. GitHub's own commit-level `statusCheckRollup.state` and `gh pr checks` ignore the superseded runs. Reading every context reported FleetDeck #31 red on an all-green head (2026-10-14).

A check's identity is (app slug, workflow databaseId, workflowRun.event, name). The event matters because one workflow's push run and pull_request run are two checks. The latest run is the highest CheckRun databaseId: a queued re-run already has one, while startedAt is null until it starts. A row whose identity cannot be read is kept rather than collapsed, and so is an Actions row with no workflow run. Fixed in agent-fabric `for/user/gate-latest-run` e3a0ba11 (`pr_gate.latest_runs`).

Trap: `review_status.base.obj(None)` returns `{}`, not None. A null field passes an `is None` guard, so check the leaf value's type instead.

`tools/fabric/results.py` (not in my entry) still counts every run.

*Observed 2026-10-14 (devex-tooling)*

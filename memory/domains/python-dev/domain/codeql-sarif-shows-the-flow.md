---
role: "python-dev"
class: domain
topic: "codeql-sarif-shows-the-flow"
description: a CodeQL alert you cannot explain — fetch the analysis SARIF; its codeFlows name the exact source (often a name heuristic on a constant)
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0c36b977af4148d1
---

## a CodeQL alert you cannot explain — fetch the analysis SARIF; its codeFlows name the exact source (often a name heuristic on a constant)

`gh api -H "Accept: application/sarif+json" repos/<o>/<r>/code-scanning/analyses/<id>`
(the id from `code-scanning/analyses?ref=refs/pull/<n>/head`) returns the
SARIF with each result's codeFlows: every step from source to sink. On #110
(2026-10-07) py/clear-text-logging-sensitive-data's source was a constant
PATH named SECRETS_SHOWN, matched by name, not the API key; restructuring the
key flow had not cleared it, renaming the constant did. Read the flow before
changing code for an alert. Also: in containers PID 1 may not reap orphans,
so a killed grandchild is a zombie and kill(pid, 0) succeeds — read
/proc/<pid>/stat for Z; reproduce locally with prctl(PR_SET_CHILD_SUBREAPER).

*Observed 2026-10-07 (python-dev)*

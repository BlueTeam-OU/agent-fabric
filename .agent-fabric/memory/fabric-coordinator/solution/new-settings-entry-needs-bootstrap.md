---
role: "fabric-coordinator"
class: solution
topic: "new-settings-entry-needs-bootstrap"
description: "A new hook entry in workspace/settings.json reaches a login only at its next bootstrap; the launcher's pull carries code, not rendered settings — put new behaviour behind an entry that already exists"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cf4dae43bb555d77
---

## A new hook entry in workspace/settings.json reaches a login only at its next bootstrap; the launcher's pull carries code, not rendered settings — put new behaviour behind an entry that already exists

#464 (j510), review round 1 F1. I moved the ADR-038 r9 shell seal out of session-start.py into a new workspace
SessionStart entry. A login whose launcher pulled the new code (`keep_fabric_current` runs `pull_ff` and re-execs)
keeps its old rendered `<projects>/.claude/settings.json`. That file is written only by `bootstrap.py
workspace_settings` (bootstrap.sh, or `fabric-ctl upgrade fabric`). Such a login therefore ran the new
session-start.py, which no longer sealed, and had no entry for the new script: no seal at all, and nothing said so.

**Why:** code and rendered settings move at different times. A change that splits behaviour across both breaks for
every account in between.

**How to apply:** new behaviour that must hold on every account goes into code that an existing entry already runs
(here, session-start.py calls session-seal.py by path). A new settings entry is acceptable only for something that
may be missing until the next bootstrap. The review lens that found it is incomplete-migration ("an installed copy
the repository moved ahead of"). Related: [[launch-time-change-needs-relaunch]], [[j510-session-seal-managed]].

*References: j510-session-seal-managed, launch-time-change-needs-relaunch*

*Anchors: `tools/fabric/launch.py::keep_fabric_current`, `tools/fabric/bootstrap.py::workspace_settings`*

*Observed 2026-11-03 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: workflow
topic: "fleetdeck-pr-title-conventional"
description: fleetdeck (herdr fork) CI checks the PR title as a conventional commit; a title edit does not rerun it, close and reopen does
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 5b1977b1b848dd78
---

## fleetdeck (herdr fork) CI checks the PR title as a conventional commit; a title edit does not rerun it, close and reopen does

BlueTeam-OU/agent-fabric-fleetdeck's CI job `conventional-commits` runs
`scripts/conventional_commits.py "$PR_TITLE"`, so a drain PR titled the
agent-fabric way ("memory: the drain of …") goes red; use
`chore(memory): …` (check it locally with that script first). The
workflow triggers only on opened/synchronize/reopened, and a rerun reuses
the old event's title, so after `gh pr edit --title` the check stays red
until the PR is closed and reopened (done on #63, 2026-11-09).

*Anchors: `.github/workflows/ci.yml::types: [opened, synchronize, reopened]`, `.github/workflows/ci.yml::conventional_commits.py`*

*Observed 2026-11-09 (fabric-coordinator)*

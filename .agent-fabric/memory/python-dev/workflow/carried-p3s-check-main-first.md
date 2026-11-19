---
role: "python-dev"
class: workflow
topic: "carried-p3s-check-main-first"
description: "j139: a request to fix carried review P3s found all six already fixed on main by later follow-up commits"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d1144f2528557970
---

## j139: a request to fix carried review P3s found all six already fixed on main by later follow-up commits

Carried P3s (#584 F6-F9, #594's two) were already fixed by follow-up commits (e.g. 63032386) after the review texts that still said "not fixed". Read the code and `git log -S` on origin/main before planning work; the review body is stale evidence.

**Why:** j139 ended with zero commits, only verdicts.
**How to apply:** per finding, cite the line that shows it fixed; run the covering test, plant one mutation on the guard, restore from a backup copy, then reply and `done --no-artifact`.

*Observed 2026-11-17 (python-dev)*

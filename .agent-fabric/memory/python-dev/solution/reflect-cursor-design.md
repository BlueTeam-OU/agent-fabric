---
role: "python-dev"
class: solution
topic: "reflect-cursor-design"
description: "fabric-reflect (ADR-058) cursor design lessons: rowid position, failed sends, closing exactly the shown pass"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - beca53b917304aa0
  - ea2e5f850cdaf924
---

## fabric-reflect (ADR-058) cursor design lessons: rowid position, failed sends, closing exactly the shown pass

Checked against origin/main 2026-10-20: every lesson holds. `tools/fabric/reflect.py` still keeps the cursor (`cursor`, journal rowid + episode id in reflect-cursor.json), and `secretstore/statecopy.py` `STATE_FILES` still lists `reflect-cursor.json` (the later new-agent change touched other lines, not this). Lessons: a retried send updates the SAME episodes row, so failed/pending rows are read and tagged, never skipped; a bare `done` must close exactly the shown pass (`done --through N`, required since j38); the cursor checks its episode id against the row it names; a new journal-position state file belongs in `STATE_FILES`.

**Why:** these came out of two blind reviews; the tests alone had not caught them.
**How to apply:** for any cursor over a mutable store, test the retry-in-place case and the hint-text-closes-exactly-what-was-shown case.

*Anchors: `tools/fabric/reflect.py::cursor`, `tools/fabric/secretstore/statecopy.py::STATE_FILES`*

*Observed 2026-10-20 (python-dev)*

---
role: "python-dev"
class: solution
topic: "reflect-cursor-design"
description: "fabric-reflect (ADR-058) cursor design lessons: rowid position, failed sends, closing exactly the shown pass"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - beca53b917304aa0
---

## fabric-reflect (ADR-058) cursor design lessons: rowid position, failed sends, closing exactly the shown pass

fabric-reflect (tools/fabric/reflect.py, j37) keeps its cursor as a journal rowid plus the episode id at that row in the state file reflect-cursor.json (atomic 0600, under agent_lock).

- A retried send updates the SAME episodes row, so a pass that skips failed rows and a cursor that passes them hides the message for good: failed/pending rows are read, tagged.
- A bare `done` recomputing "the first --max after the cursor" closes unshown messages when --max differs from the pass's; the pass must print `done --through N` (both hint branches; one was a literal placeholder missing its f-prefix, caught only by the re-review). Review of #264 then decided done requires --through (j38).
- The cursor checks its episode id against the row it names: a restored/vacuumed journal keeps the owner but moves rows.
- statecopy.py STATE_FILES must list any new state file that is a position in the journal (reflect-cursor.json, commit 32db639c).
- #256 was closed by the coordinator and folded into their PR: reflect.py is on the lint never-list, so a python-dev PR cannot touch it; the review-fix commits go to a for/user branch.

**Why:** these came out of two blind reviews; the tests alone had not caught them.
**How to apply:** for any cursor over a mutable store, test the retry-in-place case and the hint-text-closes-exactly-what-was-shown case.

*Anchors: `tools/fabric/reflect.py::cursor`, `tools/fabric/secretstore/statecopy.py::STATE_FILES`*

*Observed 2026-10-14 (python-dev)*

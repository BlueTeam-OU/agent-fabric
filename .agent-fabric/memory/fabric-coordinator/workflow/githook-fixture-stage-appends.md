---
role: "fabric-coordinator"
class: workflow
topic: "githook-fixture-stage-appends"
description: tests/githook_fixtures.py Repo.stage(rel, text) APPENDS to the file (write(..., append=True)) — staging a JSON file twice makes it invalid; write() then git add to replace
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bb7e05017c8cadb8
---

## tests/githook_fixtures.py Repo.stage(rel, text) APPENDS to the file (write(..., append=True)) — staging a JSON file twice makes it invalid; write() then git add to replace

2026-11-03, j535 (#467): a pre-commit case wrote policies/state-writers.json with `repo.write()` and then
`repo.stage(same path, same json)`; the staged blob was two JSON objects concatenated and the hook said
"not JSON". `Repo.stage` and `Repo.commit` append; `Repo.write(rel, text)` replaces (append=False default).

**Why:** the name reads as "stage this content"; it is "append this content and add -A".
**How to apply:** to stage a replaced file, `repo.write(rel, text)` then `repo.git("add", rel)`.
Related: [[hook-fixtures-copy-module-list]].

*References: hook-fixtures-copy-module-list*

*Anchors: `tests/githook_fixtures.py::def stage`*

*Observed 2026-11-03 (fabric-coordinator)*

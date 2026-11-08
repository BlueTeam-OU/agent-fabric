---
role: "python-dev"
class: solution
topic: "harvest-applied-correction-cases-j114"
description: "j114 #494: harvest does not re-file an applied correction in cases (a) inference and (b) legacy entry; why, and the review/arming traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 86c6e975939c74d9
---

## j114 #494: harvest does not re-file an applied correction in cases (a) inference and (b) legacy entry; why, and the review/arming traps

#494 (merged 2026-11-05) pins two cases, harvest unchanged. (a) The assembler lists only the author's own merge_target (writer.py gates on `_inferred_target`; collisions.py waves an authorised target past inference), so an inference never removes the entry; an inferred-only move has no merge_target and is a plain memory. (b) Every entry the writer made has all six fields since 4db1ff44 (895 entries on this host, 0 without applied_key), so a legacy shape is hand-made; a fallback by memory name + replaced heading would skip a correction rewritten under the same name, which only the key tells apart.

**Why:** the review's M1 mutation (skip by memory name + replaced) survived until a same-name rewritten correction was a case; a "Kills:" docstring line must be proved by planting the mutation.
**How to apply:** `_report_case` helper drives the harvest over a planted report. A wait loop on `^exit ` matched test output; use a unique marker (`RESULT n`). Re-review needs `fabric-review save 494 1` of the posted body (`gh api .../reviews/<id> --jq .body`) before `fabric-review next`. A P3 left "partly" by a re-review stays open in the chain: arm with `--defer "<head8>:F<n>" "<why>"`. Push needs the gh credential helper ([[git-signing-key-for-agent-accounts]]).

*References: git-signing-key-for-agent-accounts*

*Anchors: `tools/fabric/harvest_memory.py::applied_corrections_of`, `tests/test_harvest_memory.py`*

*Observed 2026-11-05 (python-dev)*

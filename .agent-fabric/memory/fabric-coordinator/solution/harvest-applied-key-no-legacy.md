---
role: "fabric-coordinator"
class: solution
topic: "harvest-applied-key-no-legacy"
description: "does the memory harvest re-file an applied correction (same-run inferred move, entry without applied_key)? no; pinned"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f85330f5e212d039
---

## does the memory harvest re-file an applied correction (same-run inferred move, entry without applied_key)? no; pinned

The harvest (`tools/fabric/harvest_memory.py`) does not file an applied correction again. Both suspected holes from #486 are
closed by tests merged in #494 (`tests/test_harvest_memory.py`, the cases at "applied and moved by inference in one run" and
"legacy entry without an applied_key"). An applied_corrections entry without `applied_key` exists nowhere: 2026-11-05, 68
`last-drain-report.json` files under ~/projects (1782 entries) and 18 committed versions on main (468) — 0 missing. Such an
entry is deliberately treated as no correction (its memory is filed): matching by name+heading would skip a rewritten correction.
The remaining replay path (an entry `holds()` prunes) is stopped by the assembler's replaced_sections, pinned in
`tests/test_assemble_passes.py`. Reopen only if a report lacking `applied_key` turns up somewhere (job j611 closed on this).

*Anchors: `tools/fabric/harvest_memory.py::applied_key`, `tests/test_harvest_memory.py::test_a_legacy_entry_without_an_applied_key_is_not_a_correction_and_its_memory_is_filed`*

*Observed 2026-11-05 (fabric-coordinator)*

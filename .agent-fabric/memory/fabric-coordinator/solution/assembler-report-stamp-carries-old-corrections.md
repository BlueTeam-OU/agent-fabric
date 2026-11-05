---
role: "fabric-coordinator"
class: solution
topic: "assembler-report-stamp-carries-old-corrections"
description: "a drain's second bundle refused REPLACED SECTION STANDS for corrections of older drains — verify_replacements trusts the report's stamp, but the merge restamps carried entries; j511 blocked on python-dev-04 (01a1952e)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d067477ee2a7eebf
---

## a drain's second bundle refused REPLACED SECTION STANDS for corrections of older drains — verify_replacements trusts the report's stamp, but the merge restamps carried entries; j511 blocked on python-dev-04 (01a1952e)

2026-11-01, rebuilding #444 (j511) on main 2b7d37ae (#445's assembler): pass 1 refused at
architect-cto-01/agent-fabric.tar with REPLACED SECTION STANDS for four corrections stamped
2026-10-12 / 2026-10-18 that none of its claims touch.

Cause: tools/fabric/assembler/shapes.py verify_replacements reads applied_corrections as "this
drain's" when the report's `stamp` equals --stamp, but slices.py's merge carries every earlier
entry and restamps the report on the first run of a new stamp (here the projects-root bundle).
Each entry has its own `stamp` (writer.py), which is the field to judge by.

Contracted to python-dev-04, REQUEST 01a1952e-b198-765b-a336-a02c9e58fa9f, critical path. A
local branch develop-qzapp/user/fix/j511-rebuild (origin/main + brand-comms topic + fixture
cherry-picks) waits in the j513 worktree; rerun ~/drain/2026-10-31/fixed/full.sh there once the
fix merges, then re-apply F11 (ugrep section) and F4 (section_writers) from 481ca42b.

**How to apply:** a refusal naming corrections that no claim of the bundle touches: compare the
entries' own stamps with the report's before suspecting the claims. Related:
[[drain-multi-pass-procedure]], [[j279-drain-2026-10-31-state]].

*References: drain-multi-pass-procedure, j279-drain-2026-10-31-state*

*Anchors: `tools/fabric/assembler/shapes.py::previous.get("stamp") == run.args.stamp`, `tools/fabric/assembler/slices.py::applied_corrections=list(applied.values())`*

*Observed 2026-11-01 (fabric-coordinator)*

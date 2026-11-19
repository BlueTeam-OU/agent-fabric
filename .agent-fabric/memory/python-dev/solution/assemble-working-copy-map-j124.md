---
role: "python-dev"
class: solution
topic: "assemble-working-copy-map-j124"
description: "j124 #535 — assemble --working-copy PROJECT=DIR reaches named anchors only; own-project form is the bare flag; review/arm traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fdfdaedc4754ed31
---

## j124 #535 — assemble --working-copy PROJECT=DIR reaches named anchors only; own-project form is the bare flag; review/arm traps

`assemble.py --working-copy` is repeatable: bare DIR or `<--project>=DIR` is the corpus checkout (two different ones refused); other `PROJECT=DIR` goes to `args.checkouts`, read by `anchorkeep.verdict` -> `memory_check.named_trees(…, checkouts)` only. `origin_trees` takes no map: in a project corpus `own_project_of` is None so it always returns the tree (a map there was dead code, caught by mutation thinking, not by a test). A self-named `<project>:` anchor in a project corpus is judged beside the tree by id (pre-existing); assemble does not load a mapped project's hygiene list (pre-existing, not fixed).
**Why:** the 2026-11-08 drain kept checkouts under its own wt/ dir, lint got them by flag, the guard saw none and read the corpus anchor as unknown.
**How to apply:** review round traps — `git checkout <file>` to undo a mutation also drops your uncommitted real edit; `fabric-review next` needs `fabric-review save <pr> 1 < report` first and `card_base` in the request; a retyped report is not verbatim, so post only the final one; arm with `--defer "<head8>:F<n>" "<why>"` for carried P3s. Owner's "arm N" does not waive the review gate.

*Anchors: `tools/fabric/assembler/intake.py::checkouts`*

*Observed 2026-11-09 (python-dev)*

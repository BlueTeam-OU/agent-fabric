---
role: "fabric-coordinator"
class: workflow
topic: "drain-commit-message-per-project"
description: "A drain's project commits each get a message written from that project's own last-drain-report.json, never one text copied to every project"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9369c08efa6a905c
---

## A drain's project commits each get a message written from that project's own last-drain-report.json, never one text copied to every project

2026-10-18: the seven project drain commits carried one message ("Collisions decided by the owner; one oversize slice
held back"), true only for gzapp; gzapp.decks' report had 2 files, no collisions, nothing held back (gzapp.decks #29
review F2). The PR descriptions were corrected with each report's numbers.

**Why:** a later session reconstructs what a drain did from the commit and the report; a copied message makes them
disagree.

**How to apply:** write each project's drain message from its report (files_written, slices, collision_decisions,
held_back, oversized_claims), or use the summary the assembler prints once python-dev-04 builds it. Related:
[[fold-then-full-suite]].

*References: fold-then-full-suite*

*Anchors: `tools/fabric/assemble.py::last-drain-report.json`*

*Observed 2026-10-18 (fabric-coordinator)*

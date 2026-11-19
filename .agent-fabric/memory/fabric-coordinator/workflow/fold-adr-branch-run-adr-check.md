---
role: "fabric-coordinator"
class: workflow
topic: "fold-adr-branch-run-adr-check"
description: after merging an older branch that amends ADRs into another, run adr.py check on the merge before pushing; a clean merge can leave DIGEST bullets out of date order
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d36e0ff4cfd5ba42
---

## after merging an older branch that amends ADRs into another, run adr.py check on the merge before pushing; a clean merge can leave DIGEST bullets out of date order

Folding the j706 branch (cut before 2026-11-08) into the j725 branch merged
cleanly, but git put ADR-064's 2026-11-11 DIGEST bullet above two 2026-11-08
bullets main had added since. `adr.py check` refuses that, and every
platform-smoke leg failed on it (run 43021170024; fixed in 98e4b8d1). The
guards-and-suites legs stayed green, so a green first CI job does not clear it.

**Why:** a textual merge has no notion of the DIGEST's date-order rule.
**How to apply:** after any merge that brings in ADR amendments, run
`python3 tools/fabric/adr.py check` before you push. When you move a bullet,
check that its neighbour isn't a wrapped bullet, whose continuation line must
stay attached. Related: [[adr-range-check-before-push]].

*References: adr-range-check-before-push*

*Anchors: `tools/fabric/adr.py::out of date order`*

*Observed 2026-11-11 (fabric-coordinator)*

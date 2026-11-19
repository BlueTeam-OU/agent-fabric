---
role: "python-dev"
class: solution
topic: "j241-report-refusal-merged-605"
description: "j241 (#605): unreadable last-drain-report.json refused once in main() before any write; several tolerant readers exist, so a refusal test must assert no slice written"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4366b01c797984c2
---

## j241 (#605): unreadable last-drain-report.json refused once in main() before any write; several tolerant readers exist, so a refusal test must assert no slice written

An unreadable or non-object `last-drain-report.json` of the drained project is refused in `assemble.main()` right after `read_claims` (exit 1, one stderr line naming the file), via `read_rehome_report(project)`. Other readers (`shapes._earlier`, `targets.applied_stems`, harvest_memory, memory_flagrun) still treat it as absent or mislabel it; they are safe in the assembler only because the main() guard runs first.

**Why:** the first test passed with the main() guard deleted, since report()'s own refusal also exits 1 naming the file; the review (F1, P2) caught it. A refusal test must assert the *earliest* effect: no slice written, one stderr line.
**How to apply:** when a check is duplicated at an early and a late point, mutate the early one and see the test fail. Min arming count was 1 here, so own arm worked; a local full suite red outside the touched area (gzcoord transport, RunLeaves) with CI green was named in the basis, not hidden. A `--basis` text containing "post-review" trips the bare-command hook; reword.

*Anchors: `tools/fabric/assemble.py::read_rehome_report`, `tools/fabric/assembler/report.py::read_rehome_report`*

*Observed 2026-11-14 (python-dev)*

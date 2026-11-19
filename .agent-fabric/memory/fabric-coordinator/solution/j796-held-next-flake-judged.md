---
role: "fabric-coordinator"
class: solution
topic: "j796-held-next-flake-judged"
description: "test_jobs_switch \"held: next is switch\" memory-unchanged flake — cause, fix (#579), and how it was judged closed"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 75b27b0340ad38f4
---

## test_jobs_switch "held: next is switch" memory-unchanged flake — cause, fix (#579), and how it was judged closed

The "held: next is switch" red (main ab101b34, #567; green on rerun) was a test defect, not a switch defect:
`settle.started_at` is whole seconds and `memory_changed` counts a file only when `newest > since`, so memory the
test wrote at World creation read as unchanged whenever the job's start fell in the next second. python-dev-04
fixed it in j113, BlueTeam-OU/agent-fabric#579 (merged 5e3d3e5c, 2026-11-13): the case calls `w.memory()` before
`sw("next")`, and pinned-clock cases fix the boundary (before / == start unchanged, after changed).

Judged 2026-11-13 (j796): read `tools/fabric/jobsparts/settle.py` memory_changed against the new cases (they agree);
main CI after the merge green on all platforms but one red (cc6072a7, debian, a different suite), where the
held-next check printed `ok`. To judge a flake fix: read the comparator, then grep each later main run's
failed log for the check's own label, not just the run's conclusion.

*Anchors: `tools/fabric/jobsparts/settle.py::if newest <= since:`, `tests/test_jobs_switch.py::held: next is switch`*

*Observed 2026-11-13 (fabric-coordinator)*

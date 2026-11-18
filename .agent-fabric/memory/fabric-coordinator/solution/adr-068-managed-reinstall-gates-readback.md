---
role: "fabric-coordinator"
class: solution
topic: "adr-068-managed-reinstall-gates-readback"
description: "After ADR-068's dispatcher merged (#546, e124a0f2), `fabric pr <verb>` walks past the installed job-copy guard until the owner reinstalls managed settings; rule 9's read-back waits on that"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1162562980da1bf2
---

## After ADR-068's dispatcher merged (#546, e124a0f2), `fabric pr <verb>` walks past the installed job-copy guard until the owner reinstalls managed settings; rule 9's read-back waits on that

2026-11-11, j723: #546 (dispatcher + ADR-068 rule 7 hook adoption) merged at e124a0f2 and reached all 30 accounts (`fabric-ctl all status` fabric column), and `~/.claude/settings.json` carries the `Bash(fabric <noun> *)` allow rules. But the guards run from the root-owned managed snapshot (ADR-043 rule 2), still fabric-80e612ff, which predates rule 7.

Measured: the snapshot's `job-copy-guard.py` fed `fabric-pr arm 999` from the main checkout denies (control); fed `fabric pr arm 999` it returns nothing (allow). main's copy denies both. So the new spelling is a live guard bypass until `sudo fabric-managed install --sha <main>` runs (owner's, ADR-043 rule 9).

**Why:** a merge that changes a guard's recognition is not in force at distribution; the managed snapshot is a third step after merge and `fabric-ctl all upgrade fabric`.
**How to apply:** for ADR-068 rule 9 (and any guard change), the live read-back starts only after `fabric-managed check` says in force; check it before announcing a new command form. Run fabric-managed by path (`bin/fabric-managed`), it is not on PATH. See [[adr-067-wave-3-started]].

*References: adr-067-wave-3-started*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::canonical`*

*Observed 2026-11-10 (fabric-coordinator)*

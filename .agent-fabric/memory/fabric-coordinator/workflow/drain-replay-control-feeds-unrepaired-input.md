---
role: "fabric-coordinator"
class: workflow
topic: "drain-replay-control-feeds-unrepaired-input"
description: "verifying an assembler fix by replaying a drain — feed the bundles from before any hand repair, count the hidden .agent-fabric dirs too, and refresh sibling checkouts"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 31a509b230b3982f
---

## verifying an assembler fix by replaying a drain — feed the bundles from before any hand repair, count the hidden .agent-fabric dirs too, and refresh sibling checkouts

A replay of a drain proves an assembler fix only if its input still carries the defect. The j699 replay of #519 used the
bundles after fix_anchors.py had repaired them, so the pre-fix control and the fixed head both showed 0 anchor regressions
(j663, 2026-11-09). Feeding `drain-pre-fix/` bundles into the repaired corpus made the control live: base 2a64d4fb
reverted 15 slices with 0 anchors_kept, main a4b54d78 reverted 8 with 35 kept.

Two traps in the counting script:
- Python `glob('**/*.md', recursive=True)` skips dot directories, so `.agent-fabric/memory` (most of the corpus) was
  silently not counted. Pass `include_hidden=True` (3.11+).
- The assembler's and memory_check's anchor judges read the sibling checkouts in `~/projects/<id>` as they stand, not
  `origin/main`. `~/projects/blueteam.ee` was a 4-week-old main checkout, so a valid `blueteam.ee:` anchor read as gone.
  Fetch and fast-forward the siblings before a replay, or say which were stale.

Kit: `~/drain/2026-11-08/j663-live/` (live.sh, anchor_cmp.py, per-ref logs). Follow-up REQUEST 01a1c119 to
python-dev-03. Related: [[drain-fabric-worktree-beside-projects]], [[drain-procedures]].

*References: drain-fabric-worktree-beside-projects, drain-procedures*

*Anchors: `tools/fabric/assembler/anchorkeep.py::def verdict`, `tools/fabric/memory_check.py::def judge_anchor`*

*Observed 2026-11-09 (fabric-coordinator)*

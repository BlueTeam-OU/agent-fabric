---
role: "fabric-coordinator"
class: workflow
topic: "conflict-resolve-from-one-stage-drops-clean-hunks"
description: "resolving an interleaved merge conflict by rebuilding the file from one side's stage (:2:/:3:) silently drops the other side's clean hunks"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73cb75a99e82db57
---

## resolving an interleaved merge conflict by rebuilding the file from one side's stage (:2:/:3:) silently drops the other side's clean hunks

When two sides add interleaving functions or classes, it is tempting to resolve by taking `git show :2:<file>` (ours) and splicing in the other side's whole block from `:3:`. That throws away every hunk from the other side that merged cleanly elsewhere in the file. In j747 (#546, merge ff054601) main's `own_instance_tree()` import in tests/test_githook_pre_commit.py was lost this way.

**Why:** the conflicted work-tree file holds the auto-merged hunks. A single stage holds only that side's version of them.

**How to apply:** after any rebuilt resolution, run `git diff HEAD -- f` and `git diff MERGE_HEAD -- f` (or origin/main) and read only the `-` lines. Any line one side had that is missing from the result must be restored before you commit. See [[lint-in-worktree-root]]: lint for a fabric worktree runs with `--no-siblings`, as CI does, and sibling memory drift is not this tree's.

*References: lint-in-worktree-root*

*Anchors: `tests/test_githook_pre_commit.py::own_instance_tree`*

*Observed 2026-11-10 (fabric-coordinator)*

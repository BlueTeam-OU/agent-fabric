---
role: "fabric-coordinator"
class: workflow
topic: "suite-snapshots-git-config"
description: "tests/run.sh fails if the live clone's git config changes mid-run — no worktree/branch with upstream in that clone while the suite runs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 671d385d7f5cdd88
---

## tests/run.sh fails if the live clone's git config changes mid-run — no worktree/branch with upstream in that clone while the suite runs

tests/test_session_start.py snapshots the running clone's `git config` and FAILs
("the running clone's git config changed") if it differs after. A `git worktree
add -b <b> origin/<x>` in the same clone during a background tests/run.sh writes
`branch.<b>.remote/merge` and fails the suite (2026-10-09; rerun alone: 16/16).
So: while the suite runs, do supply work in a separate clone, or use
`--no-track`, or wait for the run.

*Observed 2026-10-09 (fabric-coordinator)*

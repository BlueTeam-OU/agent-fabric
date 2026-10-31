---
role: "python-dev"
class: solution
topic: "switch-cargo-targets-j75"
description: "j75 #350 — fabric-jobs switch clears the left job's cargo targets; traps found by review and by the suites"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a45b64cbd3fc1cf8
---

## j75 #350 — fabric-jobs switch clears the left job's cargo targets; traps found by review and by the suites

`tools/fabric/jobsparts/leave_targets.py` (#350, merged 2026-10-21): `switch` clears `target` dirs beside a Cargo.toml of the left job's worktree, AFTER `mutate(commit)` succeeds (a refusal leaves everything), `--keep-targets` skips. Guards: linked worktree only (`.git` is a file), under the home, no overlap (at/above/below) with any other job's working_copy/worktree AND `choice.worktree` — `choose` can hand the next job the left job's worktree (open-PR branch), the pre-choose snapshot does not show it (review F10; I had wrongly dropped it as redundant). Unknown is kept: unreadable /proc, config (lstat: only ENOENT/ENOTDIR is absent; `ValueError` covers non-UTF-8 TOML), dir, lock.

**Why:** the first head deleted the targets of any other checkout the field lay above/below, ignored configs above the worktree, and a non-UTF-8 config hid already-done removals behind one warning.

**How to apply:** a new part must be added to `ORDER` in tests/test_jobs_parts.py; generic files must not name a managed project (lint, test_project_import/test_roots_readers fail); ruff runs in `tests/static.sh` (unused variable broke a full run). Switch tests need clean trees (commit sources, ignore `target`) and `World(under=home)` since the step requires the home. Size = unique inodes x st_blocks. The policies/agent-jobs/SKILL.md sentence is the coordinator's (F8). Arming minimum was 1 work commit in this repo (dry-run said so).

*Observed 2026-10-21 (python-dev)*

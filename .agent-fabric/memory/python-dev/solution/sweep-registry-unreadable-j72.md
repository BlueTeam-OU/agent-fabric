---
role: "python-dev"
class: solution
topic: "sweep-registry-unreadable-j72"
description: "j72 #337 - an unreadable session registry keeps worktrees; sweep suites need a readable empty registry AND their own TMPDIR, or a run deletes the real scratch"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 46ee4bd36c821830
---

## j72 #337 - an unreadable session registry keeps worktrees; sweep suites need a readable empty registry AND their own TMPDIR, or a run deletes the real scratch

`fabric-branches --sweep` (agent-fabric #337, j72): `REGISTRY_UNREADABLE` (set in `run()` and in `report_json`, from `live_sessions() is None`) makes `worktree_state` return "session registry unreadable" for a worktree with no other reason; `--json` reads it too, so the control plane's removable count agrees with the sweep. Only the worktree report line carries the reason: a kept worktree is never in `wt_remove`, so no `KEPT worktree` line prints.

**Why (traps):** (1) A suite that relied on "no registry" to see a worktree removed must now give the sweep a readable empty registry (`sessions/` dir). A readable empty registry reads every scratch dir under `$TMPDIR/claude-<uid>` as an ended session's and deletes it: my first run of test_control_branches wiped this login's real session scratch (task outputs included). Every such suite needs its own `TMPDIR` as well. (2) `python3 -m unittest` does not run the script-style suites (test_fabric_branches_cli, test_jobs_switch): run `python3 tests/<x>.py` or `tests/run.sh python`, and list the suites that grep `"--sweep"`. (3) A full `tests/run.sh python` over 600 s needs a background timeout above the default; two load flakes (test_jobs relay read 15 s, test_review_bash_guard_cli 20000 words) passed alone.
**How to apply:** after changing the sweep's registry handling, run the five sweep suites as scripts, with `TMPDIR` pointing at a scratch dir, never the session's. The brief's re-review needs a request whose range is the first round's pinned shas (`fabric-review next` refuses `HEAD`).

*Anchors: `tools/fabric/branches.py::worktree_state`, `tools/fabric/branches.py::report_json`*

*Observed 2026-10-20 (python-dev)*

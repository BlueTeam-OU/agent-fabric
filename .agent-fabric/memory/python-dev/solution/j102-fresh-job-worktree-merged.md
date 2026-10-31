---
role: "python-dev"
class: solution
topic: "j102-fresh-job-worktree-merged"
description: "j102/j474 #432 merged — fresh job starts in worktree, AGENT_FABRIC_ROOT stamped, working_copy follows worktree; the sweep/settle consequences and test traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 277204656ca612ed
---

## j102/j474 #432 merged — fresh job starts in worktree, AGENT_FABRIC_ROOT stamped, working_copy follows worktree; the sweep/settle consequences and test traps

#432 merged 2026-10-30 (head 6466db3f; 2 work, 3 fix; armed on the coordinator's AUTHORIZES word because launch.py/currency.py are security-boundary under 8 work).

- jobsparts `transition()` sets `working_copy` with `worktree` (switch, pause). Consequence found in review: the leave sweep removes a delivered job's worktree, so `settle.checkout_of(job)` falls back to `records.working_copy_of(project)` when the working copy is gone; every settle git call goes through it.
- clean_targets ignores a working_copy equal to the worktree; after_leaving and `_worktree_path` use `vcs.main_checkout`.
- `project --working-copy <own worktree>` is accepted only for the job's own project and only syncs working_copy (no project_from change).
- A mutation that survived: `_worktree_path` main-checkout base had no test; a test calling a helper directly does not cover its call sites (test via `settle._branch_tips`).

**Why:** launcher relaunch chdir'd into a stale working_copy and ran stale code.
**How to apply:** a fixture setting a job's `worktree` for one case must clear it for later cases (it now wins over working_copy in launch.py). A test must not run the real launcher with an empty AGENT_FABRIC_ROOT (CODE_ROOT is the live tree, fetches origin): copy tools/fabric into the fixture fabric and run that copy.

*Anchors: `tools/fabric/jobsparts/settle.py::checkout_of`, `tools/fabric/jobsparts/vcs.py::main_checkout`, `tools/fabric/jobsparts/records.py::fields[worktree]`*

*Observed 2026-10-30 (python-dev)*

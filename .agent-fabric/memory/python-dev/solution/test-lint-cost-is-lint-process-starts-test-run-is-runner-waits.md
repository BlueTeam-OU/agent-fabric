---
role: "python-dev"
class: solution
topic: "test-lint-cost-is-lint-process-starts-test-run-is-runner-waits"
description: "j140 profile — test_lint is 206 lint subprocesses at ~0.36 s CPU; test_run is runner-constant waits; where the test side can cut"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f97405b8e97c44ea
---

## j140 profile — test_lint is 206 lint subprocesses at ~0.36 s CPU; test_run is runner-constant waits; where the test side can cut

tests/test_lint.py: 89 cases, 206 `run_lint` subprocesses, ~75 of ~90 s CPU; make_base costs 8 ms, git 2 s, so the only lever test-side is fewer lint starts (in-process stays off, owner D6). A loop that rewrites one file per iteration cannot be batched; a loop over independent entries can ride one run if each entry gets its own file or key and the finding names it (secrets: leakN.md; control chars: ctl.kN keys added to the default dictionary). Done on j140 (95947d11-era): 21 starts fewer, CPU median 75.9 -> 66.7 s on main, 71.4 -> 67.9 s on #637's lint.

tests/test_run.py: ~34 s CPU over ~100 run.py runs at 0.3-0.7 s each, 79 s wall mostly waits fixed in the runner (run_python_suites 10 s pipe wait, STOP_GRACE_S 5 s, budget 1-2 s); no env seam, so nothing to cut test-side without a runner seam (not python-dev's file).

**Why:** the next speed job on these suites should not re-profile. **How to apply:** ask the runner's owner for a seam before touching test_run waits; per-check profile = wrap `check` and diff rusage.

*Observed 2026-11-17 (python-dev)*

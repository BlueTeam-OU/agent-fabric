---
role: "python-dev"
class: solution
topic: "deadline-from-module-start-tests-reset-clock"
description: "review-bash-guard ceiling counts from module STARTED; tests must reset mod.STARTED per judged() call; the CPU-spin case flakes under load at base too"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3c8b1f2118310e6a
---

## review-bash-guard ceiling counts from module STARTED; tests must reset mod.STARTED per judged() call; the CPU-spin case flakes under load at base too

j61 (#354 round 1): `runtime/claude-code/hooks/review-bash-guard.py` takes `STARTED = time.monotonic()` at import and `judged()` subtracts the elapsed time from the 8 s ceiling. A test that loads the module once and calls `judged()` repeatedly leaks earlier cases' time into later ones, so tests go through a `fresh()` that resets `mod.STARTED`.

A "cannot lengthen" check needs the lengthening to show: BUDGET=100 with a 30 s verdict must be "slow" in under 9 s; mutate-removing `min()` made it fail ("None after 30.0 s").

**Why:** the spin case ("spins on CPU past 3 s ... slow") returned 'error' under full-suite load, and once at base with the patch stashed, so it is an existing flake (rusage under CPU_BUDGET_S-0.1), not the patch. See [[rlimit-cpu-equal-limits-sigkill-not-sigxcpu]].

**How to apply:** when touching this guard's timing, rerun the file alone 3 times and at base before blaming the change.

*References: rlimit-cpu-equal-limits-sigkill-not-sigxcpu*

*Anchors: `runtime/claude-code/hooks/review-bash-guard.py::STARTED`*

*Observed 2026-10-22 (python-dev)*

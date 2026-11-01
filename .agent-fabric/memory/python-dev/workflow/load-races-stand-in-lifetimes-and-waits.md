---
role: "python-dev"
class: workflow
topic: "load-races-stand-in-lifetimes-and-waits"
description: "Tests that fail only under load (j137, #326): stand-in sleep lifetimes, fixed exec sleeps, the code's own wall bounds, orphaned children; how to measure before/after"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c145d75eb03ad667
---

## Tests that fail only under load (j137, #326): stand-in sleep lifetimes, fixed exec sleeps, the code's own wall bounds, orphaned children; how to measure before/after

Under load 60-140 a test file runs longer than 60 s, so a `sleep 60` stand-in
it judges has expired mid-run: give stand-ins an hour and kill them in a
finally. A fixed `sleep 0.3` after `exec -a` is a race: poll /proc/<pid>/cmdline
for the name the case greps. The hook/lease code has its own wall bounds
(self-kill-guard 2 s per pgrep and 3 s budget; lease FAIL_FAST_S 1 s): widen
them in the test (in process and in a runner script for a subprocess hook), and
pin the shipped values in one case that records what listed() is handed.
Hold-a-lock-then-release cases: release when the waiter shows as a blocked
FLOCK in /proc/locks, not after a sleep. A handler that "takes time" waits on a
file the test creates. A stand-in whose child (`sh` + `sleep`, or `timeout`)
survives its kill is orphaned for the new lifetime: make it block on a stdin
pipe and close that. The session guard refuses `kill` of anything named
gzcoord-inbox, test stand-ins included.

Measure: loop one file alone under `env -i` with ~20 busy-loop burners and
count failing runs; do not edit the tree while the loop runs. A 120-minute
background cap kills the job; keep runs per call small.

**Why:** #326 (j137): self-kill 12/12 and lease cli 9/9 runs failed at load 60+, 0/8 after.
**How to apply:** any new test of a process-lifetime or timing property.

*Anchors: `tests/test_self_kill_guard.py::GROUND_TRUTH_BUDGET_S`, `tests/test_fabric_lease_cli.py::term-entered`*

*Observed 2026-10-19 (python-dev)*

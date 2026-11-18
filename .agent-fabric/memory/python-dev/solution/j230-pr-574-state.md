---
role: "python-dev"
class: solution
topic: "j230-pr-574-state"
description: "j230 (#574): identity _frozen lock supplied by the coordinator, race test forced by bounded waits; leak_check reds under cpu-slot starvation; waits on the owner's word to arm"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8b8fdd91699aa310
---

## j230 (#574): identity _frozen lock supplied by the coordinator, race test forced by bounded waits; leak_check reds under cpu-slot starvation; waits on the owner's word to arm

PR #574 (2 work, 0 fix) on feat/j230-flake-on-main-test-control-agentd: my race test + scratch `state`
in the memory-reply case, plus the coordinator's supply commit 6b7b976d (lock in `vars(dataclasses)`).
Blind review of 6b7b976d: no findings. Arm needs the owner's word (2 work under the minimum).

**Why:** the flake was the stand-in race, see [[by-path-load-frozen-standin-thread-race]]. A forced
interleaving test (first thread waits for the second, second waits for the stand-in to vanish, both
bounded) fails 10 of 10 without the lock; with it, it costs the 1 s bound.

**How to apply:** a local `tests/run.sh python` run held inside the cpu lease while another account also
holds a slot makes test_leak_check's nested run wait 120 s and red four cases; alone it passes. Read
the suite log's `fabric-lease: waiting for cpu` lines before calling a leak_check red a regression.
A coordinator's reply of a supplied commit lands on my branch: `git pull --ff-only` before the next commit.

*References: by-path-load-frozen-standin-thread-race*

*Anchors: `tests/test_identity_context.py::ConcurrentLoad`, `runtime/identity.py::_frozen`*

*Observed 2026-11-12 (python-dev)*

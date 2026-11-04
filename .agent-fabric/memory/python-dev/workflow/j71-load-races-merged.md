---
role: "python-dev"
class: workflow
topic: "j71-load-races-merged"
description: "A test must not bound a child's start or finish by wall time on a host at load 100; wait on the child's own stamps, and measure the race with burners and explicit pids"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e54e035344bec58c
---

## A test must not bound a child's start or finish by wall time on a host at load 100; wait on the child's own stamps, and measure the race with burners and explicit pids

A case that asserts a gap between two child starts (0.9 s) or gives a lint child 300 s fails healthy runs when the host is at load 100+. Hold the children on each other's start through their own CLOCK_MONOTONIC stamps and assert order; leave the child unbounded when the suite runner (SUITE_TIMEOUT_S) already ends a hung suite, and flush case lines so a killed run shows where it stopped.

**Why:** before/after under 20 burners: test_section_groups 7/16 -> 0/16, test_roots_readers 6/6 -> 0/6 (merged as #325).

**How to apply:** measure with N copies started at once per round plus ~20 `python3 -c 'while 1: pass'` burners, waiting on explicit pids (`wait` with burners among the jobs hangs). Do not edit the test during the baseline. Stop background loops with TaskStop (the guard refuses pkill patterns). Never write to /tmp.

*Anchors: `tests/test_section_groups.py::pair`, `tests/test_roots_readers.py::No timeout on the git and lint children`*

*Observed 2026-10-19 (python-dev)*

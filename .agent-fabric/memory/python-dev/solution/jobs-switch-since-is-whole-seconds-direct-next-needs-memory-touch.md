---
role: "python-dev"
class: solution
topic: "jobs-switch-since-is-whole-seconds-direct-next-needs-memory-touch"
description: "test_jobs_switch flake \"memory directory has not changed\" — started_at is whole seconds; a case calling sw(\"next\") directly must w.memory() first"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b18d02707bfa736f
---

## test_jobs_switch flake "memory directory has not changed" — started_at is whole seconds; a case calling sw("next") directly must w.memory() first

j113: the "held: next is switch" case in tests/test_jobs_switch.py failed on almalinux CI with "your memory directory has not changed during j1". `settle.started_at` truncates the job's start to whole seconds; World() writes memory once at creation, so a job started in the next second made that file read as older than the start. `w.switch()` calls `w.memory()` first; a direct `w.sw("next")` did not. Product is right (a real write after the start has mtime >= start). Fix: commit 962e52de on branch feat/j113-flake-on-main-test-jobs-switch, `w.memory()` before the call, plus pinned-clock cases (before / same second / next second).

**Why:** a flake that is green on rerun and one-distro-only is a second-boundary race in the fixture, not the product.
**How to apply:** any new case that calls `w.sw("switch"|"next")` after `World()`/`working()` goes through `w.switch()` or calls `w.memory()` itself. Stopping a run of `tests/run.sh` by TaskStop also kills a run that was already past the lease wait; read suite.out before concluding it was still queued.

*Anchors: `tools/fabric/jobsparts/settle.py::def started_at`, `tests/test_jobs_switch.py::held: next is switch`*

*Observed 2026-11-12 (python-dev)*

---
role: "python-dev"
class: domain
topic: "mutation-run-read-rc-not-fail-count"
description: planting a mutation and counting FAIL lines passes when the test crashes or the fixture is dangling — read rc and use symlink targets that exist
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f98152a9800a6e9c
---

## planting a mutation and counting FAIL lines passes when the test crashes or the fixture is dangling — read rc and use symlink targets that exist

A mutation run that greps "FAIL" in the test output reported 0 twice in #254 for different reasons: the mutated code crashed the test before it printed (a traceback is no FAIL line), and a fixture symlink pointed at /etc/hostname, which does not exist on every host (a dangling link makes "is it followed" untestable, so the guard's removal stayed green).

**Why:** the oracle looked like it could fail and could not. A guard whose removal leaves the suite green is no evidence.
**How to apply:** print `rc=$?` beside the FAIL count for every mutation, and compare with the unmutated base run in the same loop; point test symlinks at a file the test created. Also make a check tolerate the crash it is meant to catch (catch the exception, report it as the check's detail).

*Observed 2026-10-15 (python-dev)*

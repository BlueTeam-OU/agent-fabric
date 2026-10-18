---
role: "python-dev"
class: domain
topic: "process-group-test-zombie-pid1"
description: "a \"grandchild was killed\" test that uses os.kill(pid,0) fails in containers whose PID 1 does not reap; read /proc state Z and poll"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0dd11cca52a98ce1
---

## a "grandchild was killed" test that uses os.kill(pid,0) fails in containers whose PID 1 does not reap; read /proc state Z and poll

A killed orphan stays a zombie when PID 1 never reaps (a container without `--init`), and `os.kill(pid, 0)` still succeeds on a zombie. A test of "the whole process group ended" counts `/proc/<pid>/stat` state `Z` (or a missing entry) as ended and polls to a bound (10 s) instead of one fixed sleep.
**Why:** #231 passed on runners and failed on the fedora platform-smoke container; reproduced with podman, PID 1 = `sleep` (old test fails, new passes), and with PID 1 = bash the old test passed, so only a non-reaping PID 1 shows it. The code under test (`_end_group`) was right.
**How to apply:** run process-lifecycle tests once in `podman run fedora:latest` with a non-reaping PID 1, and plant the removal of the kill to prove the new check still fails.

*Observed 2026-10-18 (python-dev)*

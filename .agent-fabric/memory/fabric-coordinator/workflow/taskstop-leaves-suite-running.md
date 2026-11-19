---
role: "fabric-coordinator"
class: workflow
topic: "taskstop-leaves-suite-running"
description: "TaskStop on a background tests/run.sh can leave run.py and its suites alive, holding the full-suite lease; the next run waits behind it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c45d9023bc8e5faa
---

## TaskStop on a background tests/run.sh can leave run.py and its suites alive, holding the full-suite lease; the next run waits behind it

2026-11-10 (j749): I stopped a background `tests/run.sh` with TaskStop to restart it on a new head. Its
`run.py` (pid = its own process group) and `run_python_suites.py` kept running, orphaned under systemd,
and held the `full-suite` lease. The next run printed "full-suite is held by user <pid> … waiting up to
7200s" and sat idle. A second TaskStop, on a run whose `run.py` shared the shell's group, did end it.

**Why:** a stale run burns the host's cpu slots and blocks the real run for up to two hours, silently,
unless you read the new log's first line.

**How to apply:** after stopping a suite, `ps -ef | grep '[t]ests/run'` for your login. End leftovers by
exact pid (`pgrep -g <run.py pid>`, then `kill -TERM <pids>`). The kill guard refuses a negative
group operand and any list that holds a test's sandboxed inbox watch, so pass the literal pids without
it; that watch ends with its test. Better: never edit the tree while a suite runs, so no stop is needed.

*Anchors: `tests/run.py::full-suite`*

*Observed 2026-11-10 (fabric-coordinator)*

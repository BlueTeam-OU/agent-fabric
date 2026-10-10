---
role: "python-dev"
class: domain
topic: "pgrep-wait-loop-matches-itself"
description: "an until-pgrep -f wait loop whose pattern is in its own command line never ends"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95bf3f84d7c30fd2
---

## an until-pgrep -f wait loop whose pattern is in its own command line never ends

`until ! pgrep -f "bash tests/run.sh"; do sleep 20; done` in a backgrounded Bash call matches
its own shell's command line, so it waits until the background limit kills it (2026-10-08, twice).
**Why:** the harness runs the whole command string under `bash -c`, and -f matches full argv.
**How to apply:** wait on a pid captured at start (`while kill -0 $pid`), or on a marker the
run writes (`echo suite=$? >> log`, then wait for that line), never on a pattern search.

*Observed 2026-10-08 (python-dev)*

---
role: "python-dev"
class: workflow
topic: "feedback-inbox-watch-alone"
description: "start gzcoord-inbox as its own background Bash call, never chained after other commands; a foreground timeout backgrounds the whole chain"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ae039eb144c6a7a0
---

## start gzcoord-inbox as its own background Bash call, never chained after other commands; a foreground timeout backgrounds the whole chain

In j68 I appended `gzcoord-inbox --until-delivery` to a foreground oracle run; the command passed 300 s, was moved to the background with the watch inside it, and ended at the 30 min limit, which left the session without a clean watch and made the stop hook ask for one again.

**Why:** the watch is one per session and long-lived; chained into a command it takes that command's fate (timeout, kill).

**How to apply:** `Bash(command: 'gzcoord-inbox --until-delivery', run_in_background: true, timeout: 7200000)` alone, after the work; run long suites with run_in_background and a log file, never with a watch behind them. Related: [[j68-hooks-port-merged]].

*References: j68-hooks-port-merged*

*Observed 2026-10-19 (python-dev)*

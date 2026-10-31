---
role: "python-dev"
class: workflow
topic: "background-waits-self-match-and-stray-watch"
description: "two shell traps while waiting on background work — pgrep -f in a wait loop matches itself; a watch started with & is unreachable and blocks the real one"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cef4b5f0f4f9c5f2
---

## two shell traps while waiting on background work — pgrep -f in a wait loop matches itself; a watch started with & is unreachable and blocks the real one

1. `while pgrep -f "<cmd>"; do sleep; done` run as a background task matches its own command line and never ends. Wait on the task's own completion notification, or match on a pid.
2. Start `gzcoord-inbox --until-delivery` only with the Bash tool's `run_in_background`. One started with a shell `&` has its output lost, so a delivery never wakes the session, and `gzcoord-inbox` then refuses the real watch ("already running") while a hook forbids killing it. Worse, the Stop hook then reports no watch.

**Why:** both cost a turn each in the 2026-10-16 session (j33/j34).

**How to apply:** one watch, tool-started, re-armed after each delivery or timeout; a multi-minute test run goes to the tool's `run_in_background` and is read from its output file.

Also: when a request says "branch off origin/main" but the work builds on a supply not yet on main, branch off the supply's head and say so in the reply.

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::watch`*

*Observed 2026-10-16 (python-dev)*

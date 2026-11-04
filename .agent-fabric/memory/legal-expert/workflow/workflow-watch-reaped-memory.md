---
role: "legal-expert"
class: workflow
topic: "workflow-watch-reaped-memory"
description: "Inbox watch killed by Claude Code for low memory: re-arming is the fabric's standing rule; do it in the same turn, after checking free memory"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 53a1d5e4debacc5b
---

## Inbox watch killed by Claude Code for low memory: re-arming is the fabric's standing rule; do it in the same turn, after checking free memory

When Claude Code reaps the background `gzcoord-inbox --until-delivery` watch for low memory (task `killed`, "restart only when asked"), the fabric's standing rule is to re-arm it: the Stop hook's text says that re-arming is the ask (`watch-on-stop.py` `ASKED`, from j366, where two sessions stayed deaf about 10 h).

**Why:** on 2026-10-24 I followed the harness note, reported the reap and left the watch stopped. The Stop hook then refused my turn, which cost a round trip.

**How to apply:** when a watch is reaped for memory, check `free -m` and re-arm it in the same turn. Report the reap only if memory is still short.

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::ASKED`*

*Observed 2026-10-24 (legal-expert)*

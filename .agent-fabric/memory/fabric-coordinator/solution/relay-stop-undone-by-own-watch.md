---
role: "fabric-coordinator"
class: solution
topic: "relay-stop-undone-by-own-watch"
description: "a deliberate relay stop does not hold on the hosting account — my own re-armed inbox watch restarts it (ensure_relay); stop hook forces the re-arm"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dd9507d759064d5a
---

## a deliberate relay stop does not hold on the hosting account — my own re-armed inbox watch restarts it (ensure_relay); stop hook forces the re-arm

2026-11-05 relay-down drill (j622): stopped `gzcoord-relay.service` at 15:50:19Z; at
16:08:24Z it was running again on the original db. `gzcoord-inbox` on the relay's own
account calls `ensure_relay`, which starts the unit when the relay is down, and the
watch-on-stop hook makes every turn re-arm the watch (after an exit 5 as well). So a
drill or an operator stop ends at the coordinator's next turn. Fleet-wide, the same
hook keeps every session spinning a 15-minute watch while the relay is down.

**How to apply:** before the next drill, j626 must land (an operator stop that holds).
Until then, don't re-arm the watch while the relay is stopped on purpose. Read-back:
docs/live-checks/2026-11-05-relay-down-drill.md. Related: [[inbox-wait-not-monitor]].

*References: inbox-wait-not-monitor*

*Anchors: `tools/fabric/gzcoord/inbox_parts/relay.py::ensure_relay`, `runtime/claude-code/hooks/watch-on-stop.py`*

*Observed 2026-11-05 (fabric-coordinator)*

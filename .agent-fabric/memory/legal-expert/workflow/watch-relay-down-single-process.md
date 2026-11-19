---
role: "legal-expert"
class: workflow
topic: "watch-relay-down-single-process"
description: "When gzcoord-inbox exits 5 (relay unreachable), wait for the relay and re-arm in ONE background command, not a poller plus a watch"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d767099ce1f8537e
---

## When gzcoord-inbox exits 5 (relay unreachable), wait for the relay and re-arm in ONE background command, not a poller plus a watch

When the inbox watch exits 5 (relay unreachable for 15 min, ADR-034 §7 step 2), arm one background command that polls the relay and then execs the watch:
`until curl -s -o /dev/null --max-time 5 http://127.0.0.1:8765/; do sleep 60; done; exec gzcoord-inbox --until-delivery`
(run_in_background, timeout 7200000, description 'gzcoord inbox wait').

**Why:** in the 2026-W44 relay drills (job j16, 2026-11), a separate poller alone left no watch, and the stop hook refused to end the turn; a poller plus a watch is two processes where the rule allows one. The combined command satisfied both.

**How to apply:** only for exit 5; a quiet exit 0 or a delivery is re-armed plainly with `gzcoord-inbox --until-delivery`.
During an announced relay-outage drill (2026-11-12, broadcast 01a1cf3c, agent-fabric ADR-064), the coordinator said to re-arm the watch "as usual". Observed: the plain watch still exited 5 after 15 min with the relay down, so this watch did not show reading InterWeave. Re-armed it plainly again, as the broadcast said.

*Anchors: `communication/gzcoord/skills/gzcoord-receive/SKILL.md::unreachable for 15 minutes`*

*Observed 2026-11-09 (legal-expert)*

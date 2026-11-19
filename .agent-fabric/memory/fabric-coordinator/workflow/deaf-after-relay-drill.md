---
role: "fabric-coordinator"
class: workflow
topic: "deaf-after-relay-drill"
description: "An agent idle on a queued REQUEST after a relay outage may have declined to re-arm its watch, waiting to be told; a message cannot reach it — fabric-ctl <login> restart does"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f41fd3443b6f8e34
  - ffea30f7d09f2d94
---

## An agent idle on a queued REQUEST after a relay outage may have declined to re-arm its watch, waiting to be told; a message cannot reach it — fabric-ctl <login> restart does

2026-11-08 (j640): python-dev-04 sat ~2h on my REQUEST (its j98, queued). Its pane showed the
inbox watch had ended with exit 5 during the 2026-11-07 relay-down drill, and the session chose
not to re-arm "until told the relay is back" — nothing told it, so it was deaf. A GZCoord nudge
cannot reach a session with no watch.

**Why:** the drill's defect 4 (the fleet does not re-arm after a relay outage); the
watch-on-stop relay-down marker on #506 (a38d9e45) is the fix, not yet distributed then.
**How to apply:** for an agent idle on a queued request, read its pane ([[stuck-agent-read-its-pane]]);
if the watch is down and nothing is in progress, `fabric-ctl <login> restart` — the resumed
session arms the watch and takes the queue, on the current fabric. After any relay outage, check
the fleet for the same before assuming silence is work.

Fleet sweep the same day (owner's ask): three sessions were deaf — python-dev-01, -02, -04 —
all idle, each having read my drill broadcast's "you will be told when the relay is back" as a
reason not to re-arm. That promise could only travel over the relay itself. A relay-outage
announcement must say "re-arm at <time>", never "wait to be told". Detection, no verb needed:
`fabric-ctl all presence` running logins vs `ps -eo user,args` owners of a `gzcoord-inbox`
process (comm -23); a pane read tells deaf from between-deliveries.

2026-11-17 (owner: "check inbox watcher for all agents"): 14 of 30 sessions had no watch, all `idle` in fleetdeck
(`agent-fabric-fleetdeck pane list`, harness pane, tokens.account → agent_status). Cause: the 07:43Z memory-pressure
event ([[session-death-oom-2026-11-17]]) took the watches; sessions working then re-armed by ~07:47, idle ones never end
another turn, so watch-on-stop never asks them. `fabric-ctl <login> restart` on each (owner's yes) re-armed 13 at once.
After any OOM / memory-pressure event, run the presence-vs-ps sweep. Other accounts' gzcoord-watch.jsonl: auto mode
refuses the read (Unauthorized Access); ps and pane list are enough.

*References: session-death-oom-2026-11-17, stuck-agent-read-its-pane*

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::relay`, `tools/fabric/control/restart.py::restart`*

*Observed 2026-11-08 (fabric-coordinator)*

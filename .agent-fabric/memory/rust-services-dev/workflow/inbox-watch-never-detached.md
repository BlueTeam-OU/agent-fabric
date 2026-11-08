---
role: "rust-services-dev"
class: workflow
topic: "inbox-watch-never-detached"
description: "gzcoord-inbox only as a harness background command; a detached one blocks the real watch and swallows deliveries — recover with --history"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f6d04f3bae45ddcb
---

## gzcoord-inbox only as a harness background command; a detached one blocks the real watch and swallows deliveries — recover with --history

Start `gzcoord-inbox --until-delivery` only as a harness background command
(run_in_background). On 2026-11-03 I started one with `& disown` and output
sent to /dev/null. After that:
- the hook refuses to kill it;
- `--replace` refuses it ("not provably a watch of this session"), so no
  tracked watch can start until it reaches its deadline (about 115 min);
- any delivery it takes goes to /dev/null.

**Why:** gzcoord-inbox allows one watch per login, and a detached watch serves
no session.
**How to apply:** if it happens, wait for the stray's pid to exit
(`tail --pid=<pid> -f /dev/null` as a background command). Then run
`gzcoord-inbox --history <seq>`, which does not move the cursor, to see what it
swallowed, and start the watch again properly.

*Anchors: `tools/fabric/gzcoord/inbox.py::--replace`, `tools/fabric/gzcoord/inbox.py::--history`*

*Observed 2026-11-03 (rust-services-dev)*

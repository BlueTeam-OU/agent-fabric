---
role: "fabric-coordinator"
class: rationale
topic: "fleet-boot-auto-order"
description: "Owner 2026-10-13 — fleet-deck start --auto: a priority queue, same-priority agents started one at a time with a delay; infrastructure before developers"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 91e07b2a011eedc1
---

## Owner 2026-10-13 — fleet-deck start --auto: a priority queue, same-priority agents started one at a time with a delay; infrastructure before developers

The owner, 2026-10-13, in the coordinator's session, after a whole-fleet restart left 23 panes at
"Enter to activate": `fleet-deck start` should manage all of boot (the owner types the key's
passphrase once), with an "auto" flag — "a priority queue with same priority agent managed with a
delay" — and "infrastructure before developer".

**Why:** the restart hit sshd's MaxStartups and per-source penalties (75 connections at once, a
passphrase prompt abandoned), and every pane then waited for a hand Enter (deck design, #115).
**How to apply:** job j176. Tiers I proposed from the deck's workspaces (only infra-before-dev is
the owner's): Coordinator → C-Level → Infrastructure → Experts → Developers; within a tier one at a
time with a 3–5 s delay; next tier once the previous is up or timed out; a login failing twice is
reported and skipped. Without --auto, panes keep waiting for Enter. Related: [[fleet-shutdown-procedure]].
Also the owner's, same day: the deck gets a menu with an item that asks for confirmation and then
runs `fleet-deck stop` (the whole shutdown, the reverse of start) — part of j176's FleetDeck half.

*References: fleet-shutdown-procedure*

*Observed 2026-10-13 (fabric-coordinator)*

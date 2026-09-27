# ADR-029 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — Actions run beside the read loop

The note this record replaced (`docs/control-plane.md`) said an action
runs beside the daemon's read loop and posts its reply when done, so a
request arriving meanwhile is still answered, and that one action at a
time per account is the action's own rule. The record dropped it
(review of agent-fabric #53). The code does it: `runtime/control/agentd.mjs`
keeps an `inflight` set beside the loop, and `upgrade.mjs` and
`secrets.mjs` answer `busy` while one of theirs runs. Rule 12 restores
it, with `fabric-ctl`'s default answer timeouts from `ctl.mjs`.

### Amendment 2026-09-27 — Rule 12 as the code has it

Rule 12, added the same day, gave `fabric-ctl`'s answer timeouts as 20 s
with two exceptions; `runtime/control/ctl.mjs` gives each operation its
own budget, and the two actions the rule names wait far longer. It also
left out that `upgrade.mjs` answers `busy` to an upgrade while a
`secrets-sync` is restarting the session (review of agent-fabric #54).
The rule now lists the budgets and the cross-kind refusal.

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

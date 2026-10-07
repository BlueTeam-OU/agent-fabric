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

### Amendment 2026-09-28 — The owner reads and adds jobs through the control plane

The owner chose a fleet view of every agent's job list, and a way to add
a job to one agent outside any session (ADR-037). The view is a read op,
`jobs`, answered for an operator only; the intake is an action,
`jobs-add`, signed like the others, whose arguments are a closed set of
plain one-line values run by argv through `tools/fabric/jobs.py`. It
names one login: a job is one agent's, and a fleet-wide job would be the
same work started many times.

### Amendment 2026-09-29 — secrets-migrate moves an account to its own store

ADR-038 moves each account's secrets from Doppler to its own store. The
move must happen inside the account, because only the account can read
its Doppler config and write its store. It must also be verifiable
without anyone seeing a value. So it is a signed action like
`secrets-sync`, with an exact test: the store has to reproduce the
`secrets.env` that Doppler gave, or the account stays on Doppler.

### Amendment 2026-09-30 — Doppler is retired: the store holds what Doppler held

Doppler is removed from the fabric (ADR-038, agent-fabric #69): every
account reads its own store, and the coordinator's templates and
signing key live in the coordinator's store. Rule 5 names the signing key's
home; rule 14, the `secrets-migrate` action, is withdrawn with the
migration it ran.

### Amendment 2026-10-06 — Each account's settings.local.json on the control plane

After ADR-038 rule 9 took the synced secrets out of every shell, the owner
asked what the agents keep in their per-clone `.claude/settings.local.json`
— a file the relay's install notes once told each clone to hold the relay
token in. No account may read another's home, and the coordinator's
login can read none of them, so the owner ruled on 2026-10-06 that the
file be manageable from the control plane, as a report and a prune of
secrets only: the account's own control agent reads and rewrites its own
file, and nothing a request carries reaches it but the operation's name.

### Amendment 2026-10-07 — Session state on the control channel

§5 rule 16 added. The operator watches the fleet through herdr, one pane
per account, and its agent panel showed only presence: whether a
session ran, read by asking every account's control agent on a timer,
never what the session was doing. The owner asked whether polling was
the right solution and whether it would reach an agent on another host,
and approved the event-driven design: the harness's own hook events
(prompt submitted, tool call, permission prompt, idle, stop, end) are
written by the session's account into its own state directory, and the
control agent already running there says it on the control channel, on
a change only. Nothing new listens on a port and no account is asked;
the display reads one stream. A second host needs only what §7
already names, a relay its daemons reach.

Live: a hook payload on the coordinator's account reached
`fabric-ctl states` as blocked within seconds, and its end as none.

### Amendment 2026-10-07 — secrets-selftest proves an account's own secrets

§5 rule 17 added. The owner asked that every agent be able to add, use
and delete secrets in its own store, in the most secure way, and know
how. The action is how the operator verifies it per account without a
value ever leaving the account: the reply carries the steps and the
verdict only. Delete is hygiene: what the store no longer holds is not
used.

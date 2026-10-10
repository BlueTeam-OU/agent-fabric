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

### Amendment 2026-10-08 — The state record names the last session and whether it can be resumed

§5 rule 16's record gains two fields. architect-cto's plan for Fleet
Deck (milestone 1, session recovery; owner-asked, 2026-10-07): the deck
re-enters an account's tab with `moveto <account> --resume`, and needs
to know before it acts whether there is a session to bring back and,
after, whether the same one came back. The plan asked for the working
copy too; it stays off the record, which carries no path: fabric-resume
finds the directory from the transcript itself.

### Amendment 2026-10-08 — The op table follows ops.mjs: disk, jobs, local, the pool and tools; three public ops

The table had fallen behind `ops.mjs`: `disk` (fe6fc8d7, the disk op),
`jobs`, `local` and the pool's ops were added by later changes without a
row here, and the six actions had none at all,
and python-dev-03's #123 adds `tools`, which it found unrecorded. Rule 4
still said `presence` was the only public op after ADR-037 rule 9 made a
role's pool listable and claimable by any placed account, for itself; a
pool claim is checked against the role the claimant's own daemon reports,
so it names nothing a relay-token holder could not already read. The
actions (`ACTION_OPS`: upgrade, secrets-sync, jobs-add, local-prune,
secrets-selftest, pool-add) now have rows too, each pointing at its
rule. A pool claim is public and writes the claimant into the holder's
pool: the one unsigned write, accepted when ADR-037 rule 9 was decided
(the owner, 2026-10-08: the agent's own list, then the role's pool) and
bounded here to one field. Review of #123.

### Amendment 2026-10-09 — pool-add's checker named; a forged claim is seen in the holder's pool file

#123's re-review (python-dev-03's PR, three P3s left on this record's text) found that rule 3 named no checker for `pool-add`'s arguments, though `pool.mjs` `checkPoolArgs` is it; that rule 4 sent a reader to `pool-list` to see a forged claim, though `pool-list` filters claimed jobs out (pool.mjs `poolList`), so the claimant is seen only in the holder's `pool.json`; and that the Scope line and the digest's keywords lagged the files and words a reader searches for. All three are corrected here; no rule's substance changes.

### Amendment 2026-10-09 — Scope: all of runtime/control/, and its Python package from Wave 8

#130's blind review found the Scope line, completed the same day, still missing jobs.mjs, secrets.mjs, local.mjs and selftest.mjs, which the rules name. A file list lags the directory it lists, and ADR-040 Wave 8 (the owner, 2026-10-09) replaces every module with a Python one. The Scope now names the directory and, from the cutover, its Python package.

### Amendment 2026-10-09 — tools-install installs a pinned account tool

python-dev-03's #126 (merged 2026-10-09) added `tools-install` to `OPS`, a signed action that runs `fabric-tools --install <tool> --json` as the account and carries its verdict back; the record had no row for it, rule 3 named no checker for its argument, and rule 12 listed neither its answer budget nor `disk`'s, though `ctl.mjs` has both. The row, the checker and the two budgets are added; the action decides nothing about which account gets a tool — `tools_install.py` installs only on an account with a working copy of a project that declares it, so the Doppler CLI stays off every other account (the owner, 2026-10-08). The first pin, Doppler 3.77.0, is `projects/registry.json`'s, its sha256 taken from the release's `checksums.txt` and matched against the asset.

### Amendment 2026-10-09 — Fleet views read through fleet.py, with two Stage 1 bridges

ADR-046's fleet views read closed jobs, which no operation returns until after the Wave 8 cutover (ADR-040 §7). Until then they read them through the host executor, the sudo fallback this record keeps for a host whose control agents are down, read-only and named in every value; `jobs --all` replaces it.

### Amendment 2026-10-10 — The gateway is installed and read through the control plane

python-dev-03's #176 (gateway-switch s4) added the `gateway-install` action and the `gateway` read; its review left the record to the coordinator. The owner armed it on 2026-10-10 and the first live install put 0.1.0, verified against the pin, on all 25 accounts.

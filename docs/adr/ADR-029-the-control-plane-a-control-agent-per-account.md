# ADR-029 — The control plane: a control agent per account answers signed actions over the relay

**Date:** 2026-09-17
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** runtime/control/, every module and the unit file, and its Python package tools/fabric/control/ from its creation (ADR-040 Wave 8); bin/fabric-ctl; the control channel's refusal in GZCoord's inbox and send tools; the unit's installation in tools/fabric/bootstrap.py; tools/fabric/local_settings.py (rule 15) and runtime/claude-code/hooks/session-state.py (rule 16); account persistence (runtime/provisioning/persist-accounts.sh, runtime/provisioning/platform/qubes/agent-fabric-accounts.rc); the fallbacks bin/fabric-usage and bin/fabric-host
**Pillar:** P5
**Evidence:** docs/live-checks/2026-09-17-control-plane.md

## 1. Context and Problem

On 2026-09-17 the first fleet usage table was made by hand, and the
second (`bin/fabric-usage`) could be made only from the coordinator's
login, through sudo, one host at a time. Anything else the coordinator
needed to know about an account — which Claude account it is signed into,
which keys it holds, how far its fabric is behind, whether a session is
running — was read the same way, by entering another account's home.
The alternative inside the fleet was to ask the agent in a session, and
an account with no session running, or a session busy with its own work,
could not answer at all.

The owner asked for a real-time control plane: a message received by a
process on the account, answered with the data asked for. What
"received" means is the whole design, because the one thing every
account already has is the relay, and a session's inbox is the one place
such records must never land.

## 2. Decision

**Every account runs a control agent** — `runtime/control/agentd.mjs`,
a daemon under a systemd user unit, alive whether or not a Claude session
is. It reads requests on a control channel of the relay the fleet's
GZCoord traffic already rides, answers what it can say about its own
account, and posts the reply. No session, no model, no prompt and no
sudo are in the loop.

- **A channel no session drains.** The records ride the relay on a
  channel of their own, `fabric:control` (`runtime/control/config.json`),
  one JSON object per relay message. They are not GZCOORD/1 messages, and
  the GZCoord tools refuse any channel whose name ends in `:control`.
- **No delivery, only reading.** Every daemon reads every record and
  answers only what names it (`to`: its address, a list holding it, or
  `*`); the coordinator reads replies by `in_reply_to`. A daemon keeps no
  cursor and acks nothing: it primes from the newest record and
  long-polls after it, so a restart never replays history, and a request
  posted while a daemon was down is not answered.
- **Reads and actions.** A closed set of read ops reports the account;
  actions change it (`sign.mjs` `ACTION_OPS`, the six rows marked
  *action* below) and are answered only when signed by the operator's
  key. One unsigned write exists, a pool claim (rule 4).

| op | what the account answers |
|---|---|
| `ping` | that it is there |
| `identity` | agent, host, role, project, working copy; the Claude account signed in and whether a credentials file exists; a setup-token by fingerprint |
| `usage` | the five-hour and seven-day windows, with the account's own token in one request header and nowhere else |
| `keys` | each synced key's name, presence and a twelve-hex-digit sha256 prefix, and whether the key git signs with has a usable secret in the keyring — never a value |
| `fabric` | head, branch, distance behind `origin/main`, dirty |
| `session` | Claude processes as the login; whether one is planning |
| `presence` | whether a session is running, a public op (ADR-030) |
| `host` | load, memory and swap, block devices, held leases, the largest processes — the same numbers from every daemon on a host, collapsed by host (ADR-010) |
| `disk` | what the account's home holds, by its largest directories, one bounded scan shared by the requests that arrive while it runs |
| `script` | the letters of the notes, the visible text, stored thinking and the locale worker's transcripts, by script and language, counts only (ADR-027) |
| `recall` | which corpus paths the account's sessions read over 24 h — index, slice, charter — paths and counts only |
| `tokens` | the login's own spend per model over a window, direct-path and broker models summed apart; the only place a login's share of a Claude account can be read |
| `memory` | the drain: the account's own harvest, in bundles (rule 9) |
| `accounts` | the Claude accounts this login observes and their usage windows (ADR-031) |
| `jobs` | the account's open jobs (ADR-037) |
| `local` | per working copy, the per-clone harness settings: env key names and which are synced secrets, permission rules by count — never a value (ADR-038) |
| `tools` | the account's tools report: every tool the bound role's projects declare, found or missing, with the report's age; written by the daemon from `fabric-tools --all --json` at start, hourly and after a rebind |
| `pool-list` | a role's open pool of jobs, a public op (ADR-037) |
| `pool-claim` | a claim of one pool job for the asker's own list, a public op, checked against the role the asker's own daemon reports (ADR-037) |
| `upgrade` | *action*: the account to the pinned Claude Code or to the merged fabric (ADR-009) |
| `secrets-sync` | *action*: the account's store projected where its tools read it (ADR-038) |
| `jobs-add` | *action*: the owner's job on the account's list (rule 13, ADR-037) |
| `local-prune` | *action*: per-clone settings entries that duplicate a synced secret, removed (rule 15) |
| `secrets-selftest` | *action*: a canary through the account's store and back (rule 17) |
| `tools-install` | *action*: the one tool named, installed from the release its project pins (`projects/registry.json` `install`: version, https url, sha256), hash checked before a byte is unpacked; skipped on an account with no working copy of a project that declares it (`tools/fabric/tools_install.py`) |
| `gateway` | read: the installed agent-fabric-gateway's version, runtime contract and digest, against `runtime/gateway.json`'s pin |
| `gateway-install` | *action*: the pinned gateway release (`runtime/gateway.json`), its SHA-256 checked before anything is extracted, the one pinned member only, run with `--version --json` and required to match the pin before it is renamed into `~/.local/bin` (`tools/fabric/control/gateway.py`) |
| `pool-add` | *action*, on the pool's holder only: a job on a role's pool (ADR-037 rule 9) |
| `status` | identity, usage, keys, fabric and session together |

- **The coordinator's side** is `bin/fabric-ctl <login|all> <op>`: one
  request, the replies read until every placed address has answered or
  the timeout is spent, and a row for each — silence included.

The sudo paths stay as fallbacks for a host whose control agents are
down: `bin/fabric-usage` for the usage windows, `bin/fabric-host <host>
drain <login>` for a drain; and, until the operations that replace them
exist, the fleet views' read of closed jobs (ADR-046 rule 5).

## 3. Alternatives Considered

- **Sudo from the coordinator's login** (`fabric-usage`, the drain by
  reading another home). Rejected as the path: one host at a time, the
  coordinator reading every account's files, and a check that is the
  coordinator's rather than the account's. It stays as the fallback.
- **Ask the session.** Rejected: an account with no session cannot
  answer, a session's answer costs a model call, and a machine record in
  a session's context is exactly what must not happen.
- **A GZCoord message type for control.** Rejected: the protocol's
  grammar is frozen and its messages are for sessions; the records are
  machine data on their own channel.
- **A consumer cursor per daemon.** Rejected: the relay's `since_id` is
  an explicit cursor, so priming from the newest record needs no state
  on the relay or on disk, and a restart cannot replay history.
- **HMAC for actions.** Rejected: a shared secret in every account would
  let any account forge the operator. Ed25519 keeps the private half in
  one login.

## 4. Rationale

The account is the one that knows its own state, and it can say so
without a model: P5's "the control plane keeps answering when a model
does not." Reading only its own home, the control agent removes the
coordinator's need to enter any other, and the drain became the first
that read no home but the account's own. A closed op set with bounded
arguments keeps a forged or malformed request from reaching a shell.
The fence is honest about what it is: it stops accidents and bounds what
a forged read can obtain to non-secret facts; only the actions carry a
proof, and the one unsigned write, a pool claim, is bounded to a job's
claimant (rule 4).

## 5. Binding Rules

1. Every placed account runs `runtime/control/agentd.mjs` under the user
   unit `agent-fabric-agentd.service` (`Restart=always`), installed and
   started by `bootstrap.sh`. The account lingers, so the unit runs from
   boot with no login and no session.
2. The control channel is named in `runtime/control/config.json` and ends
   in `:control`; `gzcoord-inbox` and `gzcoord-send` refuse such a channel with
   exit 2 before any request reaches the relay. Control records are never
   GZCOORD/1 messages.
3. The op set is closed (`ops.mjs` `OPS`). No field of a request ever
   reaches a shell. A read op takes no argument but `tokens`'s `days`, a
   number capped at 90, `pool-list`'s role and `pool-claim`'s pool id
   (`pool.mjs`); an action takes only its own closed set of
   arguments (`upgrade.mjs`, `secrets.mjs` and `jobs.mjs` `checkArgs`,
   `checkJobArgs`, `pool.mjs` `checkPoolArgs` for `pool-add`, and
   `tools.mjs` `toolsInstall`'s one `tool`, matched by `TOOL_NAME`, and
   `gateway-install`'s one `version`, a key of `runtime/gateway.json`).
4. A daemon answers a request only when its `from` is a host operator's
   address as `runtime/hosts/registry.json` places it — re-read for every
   record — or, for a public op (`PUBLIC_OPS`: `presence`, `pool-list` and
   `pool-claim`), any
   placed account's address; its `ts + ttl_s` is not past; and its id is
   not among the last 256 seen. An op is public only if its answer is
   nothing a relay-token holder could not already obtain by writing an
   operator's address on an unsigned read. `pool-claim` is the one public
   op that writes: it sets one pool job's claimant to the asker, checked
   against the role the asker's own daemon reports, and adds, removes or
   reorders no job; a forged claim takes a job off the pool for a role's
   holder. `pool-list` shows unclaimed jobs only, so the claim and its
   claimant are seen in the pool holder's `pool.json`.
5. An action (`sign.mjs` `ACTION_OPS`) is answered only when it carries
   an Ed25519 signature over its canonical form by the key the operator's
   host commits as `operator_key`; it lives at most 600 s, is refused
   when dated more than a minute ahead of the account's clock, and must
   be strictly newer than the last action accepted from its sender
   (ADR-009 §5 rule 2). The private key is only in the operator's
   own store (`FABRIC_CONTROL_SIGNING_KEY`, ADR-038), made by `fabric-ctl
   keygen` (A 2026-09-30).
6. Every request gets a reply; a section that cannot be read says so
   inline (`{"status": …}`). Replies carry no secret: keys by presence and
   a twelve-hex-digit fingerprint only, text measures as counts only, a
   memory bundle only after the harvester's credential check.
7. Every refusal but the routine ones (a reply, a request for another
   account, a duplicate) is one line in the daemon's journal.
8. `fabric-ctl` refuses, before posting, a run by a login that is not a
   host operator, except for a public op from a placed account. It exits
   1 when any addressed account stayed silent, when a drain bundle was
   short or refused, and for an action when any row is not a success. It keeps no state: the request and replies stay
   on the channel and nowhere else.
9. The drain (`fabric-ctl <login|all> memory --out <dir>`) has each
   account harvest its own memory and send each bundle in parts of at
   most 90 KiB; `fabric-ctl` files a bundle only when every announced
   part arrived, its sha256 matches, and its manifest names the account it
   came from — otherwise the row names the status and no file is written.
10. A daemon that sees its own source change exits once no action is
    running, and the unit restarts it on the new code.
11. On a host whose root volume does not persist (a Qubes AppVM), an
    account is persisted when it is created — `persist-accounts.sh` into
    `/rw/config/agent-fabric/accounts/`, re-added at boot by
    `agent-fabric-accounts.rc` — and linger is enabled in the same step.
    `/rw/bind-dirs` is never used for the account files.
12. An action runs beside the control agent's read loop, so a request
    that arrives meanwhile is still answered; one action of a kind runs
    per account at a time, and a second upgrade or `secrets-sync` sent
    while one runs is answered `busy`, as is an upgrade sent while a
    `secrets-sync` is restarting the session. `fabric-ctl` waits for an
    answer as long as the operation's own budget (`runtime/control/ctl.mjs`):
    20 s by default, 5 s for `ping`, 60 s for `tokens`, 120 s for a drain,
    200 s for `disk`, 240 s for `secrets-sync`, 300 s for `accounts`,
    330 s for `tools-install` (past the account's own 300 s bound, so a
    hung fetch is its verdict, not a silence), 300 s for `gateway-install`
    (its download bound plus two version runs), 480 s for
    `secrets-selftest`, and an upgrade's
    computed budget; `--timeout` overrides it (A 2026-09-27).
13. `jobs` is an operator's read of an account's open jobs, and
    `jobs-add` an action that puts the owner's job on one login's list
    with source `owner` (ADR-037 rules 4 and 6). Neither is public: a
    peer sees whether a session runs, never another agent's list.
    `jobs-add` names one login, never `all`, and takes a one-line title,
    topic and project id (A 2026-09-28).
**§5 rule 14 — withdrawn** (Amendment 2026-09-30): the `secrets-migrate`
action moved every account from Doppler to its own store and retired
with Doppler (ADR-038 §5 rule 8).
15. `local` is an operator's read of the account's
    `.claude/settings.local.json` files, one per working copy under
    `~/projects` and the projects root's: the `env` key names, which are
    synced secrets, the permission rules by count, the other top-level
    keys; never a value. `local-prune` is an action that removes from
    those files the `env` entries duplicating a synced secret (ADR-038
    rule 9) and nothing else; it takes no arguments, never follows a
    symlink, and writes nothing when the file changed under it. Both run
    `tools/fabric/local_settings.py` as the account; neither is public
    (A 2026-10-06).
16. A session's state — working, blocked on a person, or idle — is
    kept by the harness hook `session-state.py` in the account's own
    state directory, and the account's control agent posts it as a
    `state` record (`sessions.mjs`) when what it would say changes, and
    every ten minutes, on a state channel of its own (`config.json`
    `state_channel`, ending in `:control`), so a burst of replies on the
    control channel never buries it. The record names each live session's id, state
    and since when, the binding's role and project, and the binding's last
    session id with whether its transcript is on the account (resumable),
    which Fleet Deck reads before it re-enters a tab, never a path
    (A 2026-10-08); a session whose
    `claude` process is gone is left out. `fabric-ctl states` reads
    those records, sending no request; a record older than two
    heartbeats reads as unknown, and `--follow` prints a row when it
    changes or goes stale. A display that shows the states
    consumes `fabric-ctl states --follow --json` and never polls the
    accounts (A 2026-10-07).
17. `secrets-selftest` is an action that proves the account can add,
    use and delete a secret of its own: it runs `fabric-secrets selftest
    --json` as the login (`selftest.mjs`), which sets a canary name in
    the account's own store, reads it through `fabric-secret-run`, and
    removes it — two signed commits pushed to the store's remote. It
    takes no arguments; the reply is the verdict (`pass` or `fail`) and
    its steps, never the canary or its digest. One runs at a time per
    account, a second is answered busy (A 2026-10-07).

## 6. Consequences

- The fence is not a proof for reads: the relay verifies no sender, so a
  relay-token holder can write the operator's `from` on a read, or post a
  reply in another account's name that `fabric-ctl` prints as that
  account's row. The table is as honest as the least trusted token
  holder until replies are signed.
- A request posted while a daemon was down is lost, not queued; the row
  says `no answer`, and the operator asks again.
- One relay carries the channel: when it is down, no account answers,
  and the sudo fallbacks are the only read (ADR-010's host executor).
- A drain costs no sudo and reads no other home; a credential-shaped hit
  in a memory refuses that account's whole drain at the harvester.

## 7. Future Evolution

- Signed replies, by a per-account key the same way, so a forged row
  cannot pass as an account's.
- A second host: its daemons need a relay URL they can reach —
  `control_relay_url` for the host in the registry, exported to the unit
  as `CLAUDE_BRIDGE_URL` — and the same channel. The relay binds
  `127.0.0.1` today; nothing for a second host is built, and the
  registry has one host.
- Removing a login from the Qubes snapshot (`--forget`) waits for the
  first removal; until then a `userdel` there is undone at boot.
- A reboot of the host, read back — `getent passwd` lists every account
  and `fabric-ctl all ping` answers within seconds — has not been done.

## 8. Decision Status

Accepted. The control agent, the channel, the read ops and the signed
actions are in use on every placed account.

## References

- `runtime/control/agentd.mjs` (`accept`, `answer`, `actionLedger`,
  `watchSource`), `runtime/control/sessions.mjs`,
  `runtime/claude-code/hooks/session-state.py`, `runtime/control/ops.mjs` (`OPS`, `PUBLIC_OPS`),
  `runtime/control/sign.mjs` (`ACTION_OPS`), `runtime/control/ctl.mjs`,
  `runtime/control/upgrade.mjs`, `runtime/control/config.json`,
  `runtime/control/agent-fabric-agentd.service`, `runtime/control/tests/`.
- `bin/fabric-ctl`, `bin/fabric-usage`, `bin/fabric-host`.
- `communication/gzcoord/scripts/inbox.mjs` (`assertNotControlChannel`),
  `send.mjs`.
- `runtime/claude-code/bootstrap.sh` (the unit),
  `runtime/provisioning/persist-accounts.sh`,
  `runtime/provisioning/platform/qubes/agent-fabric-accounts.rc`.
- `runtime/hosts/registry.json` (operators, `operator_key`, placement).
- ADR-009 (the actions and fleet operations), ADR-010 (hosts and the
  host executor), ADR-013 (the drain), ADR-027 (the `script` measure).
- The live check in Evidence.

## Amendments

The body above reads current; each change's full note is in [history/ADR-029-amendments.md](history/ADR-029-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-27 | Actions run beside the read loop | §5 rule 12 added: actions run beside the read loop, one of a kind per account, a second answered busy; fabric-ctl's answer timeouts |
| 2026-09-27 | Rule 12 as the code has it | §5 rule 12: every operation's answer budget, and an upgrade refused while a secrets-sync restarts the session |
| 2026-09-28 | The owner reads and adds jobs through the control plane | §5 rule 3: `jobs.mjs` arguments; rule 13: `jobs`, `jobs-add` |
| 2026-09-29 | secrets-migrate moves an account to its own store | §5 rule 14: the migration action |
| 2026-09-30 | Doppler is retired: the store holds what Doppler held | §5 rule 5 (the signing key's home), rule 14 withdrawn |
| 2026-10-06 | Each account's settings.local.json on the control plane | §5 rule 15: `local`, a names-only read; `local-prune`, an action removing synced secrets from its `env` |
| 2026-10-07 | Session state on the control channel | §5 rule 16: the session-state hook, agentd's `state` record on change and heartbeat, `fabric-ctl states [--follow]` |
| 2026-10-07 | secrets-selftest proves an account's own secrets | §5 rule 17: the `secrets-selftest` action, a canary set, used through `fabric-secret-run` and removed in the account's own store |
| 2026-10-08 | The state record names the last session and whether it can be resumed | §5 rule 16: `last_session` and `resumable`, no path |
| 2026-10-08 | The op table follows ops.mjs: disk, jobs, local, the pool and tools; three public ops | §2 table, §5 rules 3 and 4: rows for the read ops added since; the pool's arguments; `presence`, `pool-list` and `pool-claim` public |
| 2026-10-09 | pool-add's checker named; a forged claim is seen in the holder's pool file | §5 rule 3 names `checkPoolArgs`; rule 4: `pool-list` shows unclaimed jobs only, so a claim is seen in the holder's `pool.json`; the Scope line names pool.mjs, tools.mjs and sessions.mjs |
| 2026-10-09 | Scope: all of runtime/control/, and its Python package from Wave 8 | Scope line: the directory as a whole rather than a list that lagged it; tools/fabric/control/ from its creation; the unit's installation in bootstrap.py; local_settings.py and session-state.py, which rules 15 and 16 name |
| 2026-10-09 | tools-install installs a pinned account tool | §2 table: the `tools-install` row; §5 rule 3: its one argument, checked by `TOOL_NAME`; rule 12: the `disk` and `tools-install` budgets |
| 2026-10-10 | The gateway is installed and read through the control plane | §2 table: `gateway` and `gateway-install`; §5 rule 3: its one `version` argument; rule 12: its budget |
| 2026-10-09 | Fleet views read through fleet.py, with two Stage 1 bridges | §2: the host executor's read of closed jobs is a named fallback for the fleet views until `jobs --all` exists (ADR-046) |

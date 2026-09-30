# ADR-031 — Claude accounts: which account a login runs on is assigned, applied and proved by signed action

**Date:** 2026-09-24
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the Claude-account templates (entries `CLAUDE_ACCOUNT_<ACCOUNT>` of the coordinator's store, ADR-038) and each login's `CLAUDE_CODE_OAUTH_TOKEN` (projects/registry.json `agent_env`); bin/fabric-accounts and runtime/control/accounts.mjs; the control agent's `secrets-sync` action (runtime/control/secrets.mjs) and `accounts` op (runtime/control/ops.mjs, runtime/control/agentd.mjs); the launcher's sign-in check (runtime/openrouter/launch); bin/fabric-status's sign-in line
**Pillar:** P5
**Evidence:** docs/live-checks/2026-09-24-claude-accounts.md

## 1. Context and Problem

The fleet runs on more than one Claude subscription. Until 2026-09-24 a
login ran on whatever its own `/login` sign-in was, and two things went
wrong with that. A `/login` sign-in lasts eight hours and has one refresh
holder: a refresh token shared between logins signs the others out at
the first renewal, and a fleet that fell back to its logins' own sign-ins
ran on whichever account last signed in on each. And the usage windows —
how full each account is — could be read only with a sign-in that has
the `profile` scope.

The two kinds of Claude Code token differ, as measured on 2026-09-24
(`docs/live-checks/2026-09-24-claude-accounts.md`):

| | `/login` sign-in | `claude setup-token` |
|---|---|---|
| scopes | `user:inference`, `profile`, `mcp_servers`, `plugins`, `sessions:claude_code`, `file_upload` | `user:inference` only |
| lifetime | 8 hours, renewed by the harness with a refresh token | one year, no renewal |
| holders | one | any number, at once |
| reads usage | yes | no (HTTP 403) |

On 2026-09-25 the coordinator moved eleven logins between accounts with a
host-execution loop, and the owner ruled that a move is done by the
control plane, by message: no hostexec, no sudo, nobody on the account.

## 2. Decision

**Which account a login runs on, and how full each account is, are two
mechanisms, because the two tokens can do different things.**

- **Working sessions run on a template's setup-token.** Each Claude
  account has a template: an entry of the coordinator's store, named
  after the account, holding that account's setup-token. A login runs on
  an account when the coordinator has put that template's token into the
  login's own store as `CLAUDE_CODE_OAUTH_TOKEN`; `fabric-secrets sync`
  exports it, and set, it outranks the login's own `/login`. A
  plain-claude session without it does not start (A 2026-09-30).
- **A move is assigned, applied and proved by signed action.**
  `fabric-accounts assign <login…|all> <account>` writes the token into
  each login's store, then sends every named login the signed
  `secrets-sync` action with the template's fingerprint: each account
  syncs its own secrets, proves the synced token is the template's, and
  resumes a running session on it.
- **An observer reads the windows.** The coordinator's login holds one
  `/login` sign-in per account in a config directory of its own, used for
  nothing else; its control agent reads each with the harness's own
  headless `/usage`, which renews the sign-in and makes no model call.

The credentials themselves — each login's own store, values never
printed — are ADR-012's and ADR-038's; the signed action is ADR-009's
and ADR-029's.

## 3. Alternatives Considered

- **Each login's own `/login`.** Rejected: an eight-hour token with one
  refresh holder, a browser login per login per move, and a fleet that
  silently ran on the last account signed in.
- **One `/login` sign-in shared between logins.** Rejected: the first
  renewal signs the others out.
- **A move by host execution** (sudo into each account, rewrite its
  secrets). Rejected: the account's own check is replaced by the
  coordinator's, and the running session is not brought onto the new
  sign-in.
- **Renewing the observer's sign-in without the harness.** It works — the
  harness's refresh request is visible in its binary — and is rejected: it
  would present Claude Code's client id without being Claude Code, and
  break silently when that private request changes.
- **`claude auth status` as a keep-alive.** Rejected: it starts a renewal,
  exits, and leaves a refresh lock directory that blocks the next run for
  up to a minute.
- **An `assign … own`** back to a login's own sign-in. Not offered: a
  login without a reference cannot start a plain-claude session.

## 4. Rationale

A setup-token is exactly what a working session needs — inference, for a
year, shareable — and nothing more, so a login's account is one entry
of its store, and a move is a reviewed, fingerprinted change rather than a
browser session per login. The observer keeps the one thing a
setup-token cannot do — reading usage — on sign-ins nothing else uses,
renewed by the harness the official way. The account applying and
proving its own move is P5's point: the check is the account's, the
verdict comes back, and a session survives the move.

## 5. Binding Rules

1. A template is the entry `CLAUDE_ACCOUNT_<ACCOUNT>` of the
   coordinator's store (ADR-038), holding that account's setup-token. The
   token is made once per account with `claude setup-token` in a real
   terminal, approved in a browser signed in as that account — the
   browser decides the account — and stored with `fabric-secrets store
   template-set <account>` from stdin, never pasted elsewhere
   (A 2026-09-30).
2. A login's account is the template's token, written by the coordinator
   into the login's own store as its `CLAUDE_CODE_OAUTH_TOKEN` — a write
   it cannot read back — and recorded as `<account> <fingerprint>` in the
   coordinator's own store, which is how an unchanged assignment is known
   (A 2026-09-30).
3. The launcher refuses a plain-claude session whose login's synced
   record holds no `CLAUDE_CODE_OAUTH_TOKEN` of a setup-token's shape,
   before anything starts; it takes the token from the synced record, not
   the shell. The broker path does not use it (ADR-012 §5 rule 6).
4. `fabric-accounts assign` refuses an account with no template or an
   empty one, and a login no host places. Past the store write, a move
   is messages only: every named login, changed or not, gets the signed
   `secrets-sync` action with `--expect <the template's fingerprint>`, and
   `--restart` unless `--no-restart`. With `--no-sync` no action is sent:
   each changed login applies the move at its next `fabric-secrets sync`
   (A 2026-09-27).
5. `secrets-sync` runs the account's own `fabric-secrets sync`; a synced
   token whose fingerprint is not the expected one is a failure, said by
   the account. With `restart`, a running session not already on the
   token — read from its own environment — is stopped by SIGTERM only and
   its launcher resumes the same conversation through the restart marker;
   a broker session is left alone; the requester's own session is never
   stopped; a session not stopped within 90 s is left running and its row
   fails. Any row that is not `synced` makes the command exit 1.
6. A sign-in is named by fingerprint (`setup-token <sha256 prefix>`) in
   `fabric-status`, `fabric-ctl status` and every reply, and
   `fabric-accounts templates` maps a fingerprint to its account. No
   report reads a switched login's `~/.claude.json` for its account.
7. The observer's sign-ins live under the coordinator's fabric state,
   `accounts/<account>/`, one Claude Code config directory each, used for
   nothing else; the control agent reads each every four hours and on
   request with `claude -p /usage`, caching the answer five minutes.
   `fabric-accounts list` prints signed-in state, email and expiry, never
   a token.

## 6. Consequences

- A session on a template has no claude.ai connectors, no plugins synced
  from claude.ai, no Remote Control and no web sessions; the fabric's work
  needs none of them.
- A later relaunch in any shell stays on the new account, because the
  launcher reads the synced record.
- Usage is per Claude account, not per login; a login's share is read
  from its own records (`fabric-ctl <login> tokens`, ADR-029), and what an
  account spends off the fleet's hosts is not visible.
- An account holds several valid setup-tokens at once; revoking one is
  claude.ai → Settings → Claude Code.
- The observer is one login on one host: when its sign-ins lapse or its
  control agent is down, the windows are unread until it is back.

## 7. Future Evolution

Not established: a limit on setup-tokens per account, and how the
observer behaves across a Claude Code update in the middle of a read.

## 8. Decision Status

Accepted. The templates and the observer are in use; the move by signed
action is how every account change is made.

## References

- `bin/fabric-accounts`, `runtime/control/accounts.mjs` (`templates`,
  `assign`), `runtime/control/secrets.mjs`, `runtime/control/ops.mjs`
  (`accounts`), `runtime/control/agentd.mjs` (`ACCOUNTS_KEEPALIVE_MS`,
  `ACCOUNTS_CACHE_MS`), `runtime/control/tests/accounts.test.mjs`,
  `runtime/control/tests/secrets.test.mjs`.
- `runtime/openrouter/launch` (the sign-in check), `bin/fabric-status`,
  `projects/registry.json` (`CLAUDE_CODE_OAUTH_TOKEN`).
- ADR-009 (signed actions, the restart marker), ADR-012 (credentials),
  ADR-029 (the control agent).
- The live check in Evidence.

## Amendments

The body above reads current; each change's full note is in [history/ADR-031-amendments.md](history/ADR-031-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-27 | A move without its sync | §5 rule 4 names `--no-sync`: no action is sent, and each changed login applies the move at its next sync |
| 2026-09-29 | Templates and assignments on the coordinator's store | §5 rules 1–2: a template in the coordinator's store; assign writes into the login's store |
| 2026-09-30 | Doppler is retired: the store holds what Doppler held | Scope, §2, §4, §5 rules 1, 2, 4 |

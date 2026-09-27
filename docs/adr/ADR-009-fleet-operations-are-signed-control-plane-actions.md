# ADR-009 — Fleet operations are signed control-plane actions

**Date:** 2026-09-24
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner (the control plane over sudo, 2026-09-24; account operations by signed message, 2026-09-25; distribution in the control plane and fabric commands by name, 2026-09-26); fabric-coordinator
**Scope:** bin/fabric-ctl and its `upgrade` pieces (runtime/control/agentd.mjs, runtime/control/upgrade.mjs), bin/fabric-accounts, runtime/claude-code/harness.json, the operator's signing key, distribution after a merge, runtime/claude-code/commands.json and the fabric commands' links and allow rules
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-25-first-fleet-upgrade.md, docs/live-checks/2026-09-26-first-upgrade-fabric.md

## 1. Context and Problem

Until 2026-09-24 the coordinator upgraded Claude Code on sixteen accounts
with a hand-written `hostexec` loop, and distributed the fabric with
another. Neither could bring a running session onto the new version, and
their checks were the coordinator's, not the account's. On 2026-09-25 the
coordinator moved eleven logins to another Claude account the same way;
the owner: "this process must be fully done by control plane via message."
On 2026-09-26 the loop's `git pull --ff-only origin main`, run in a
checkout sitting on a branch, fast-forwarded that *branch* to main and
reported rc=0 — harmless that time, and invisible.

On 2026-09-23 a merge was followed by a broadcast asking agents to
relaunch; the owner: a broadcast is not distribution. An agent that does
not relaunch runs on the old fabric, and one whose checkout sits on a
branch cannot launch at all.

Separately, the harness asks for approval before any command carrying a
shell expansion, whatever the mode or the rules; the inbox watch, re-armed
every thirty minutes, asked every time.

## 2. Decision

An operation on accounts is a **signed action** that each account's
control daemon (`runtime/control/agentd.mjs`, one per login, running
whether or not a session is open) verifies, performs and answers with its
own verdict — never a `hostexec` or sudo loop per login. The owner chose
the daemon over the coordinator's sudo: it already runs as each login,
needs no per-host loop and answers in real time.

- `fabric-ctl <login|all> upgrade claude [--version V]` brings each
  account to the Claude Code version pinned in
  `runtime/claude-code/harness.json`, stopping a running session
  gracefully and resuming it on the new version.
- `fabric-ctl <login|all> upgrade fabric` (PR #47, 2026-09-26) is
  **distribution after every merge, and the coordinator's duty**: every
  account's `~/projects/agent-fabric` fast-forwarded to `origin/main` and
  bootstrapped.
- `fabric-accounts assign` moves logins between Claude accounts by the same
  kind of signed message.
- Every session-facing fabric command **runs by name, with no approval
  prompt** (the owner, 2026-09-26): `runtime/claude-code/commands.json` is
  the one list.

## 3. Alternatives Considered

- **The `hostexec` loop** (sudo per login). Rejected: no session comes
  back on the new version, the checks are not the account's, and the pull
  silently moves a checked-out branch. It stays only for a daemon that
  predates a change to `upgrade` itself, and for a host whose daemons are
  down.
- **Unsigned actions over the relay.** Rejected: the relay verifies no
  sender, so any relay-token holder could claim the operator's address —
  tolerable for reports, not for an op that stops a session and installs.
- **A broadcast and the launcher's own pull.** Rejected (2026-09-23): the
  launcher pulls but never bootstraps, and a branch checkout refuses.
- **A broad allow rule, or a path through `$AGENT_FABRIC_ROOT`.** Rejected:
  a shell expansion always asks, and in auto mode a broad rule is set aside
  while a narrow `Bash(<name> *)` rule is resolved before the classifier.

## 4. Rationale

The account is the one that knows its own state; a signed action lets it
act, verify and report, and a fleet run that is not all green says so.
Pinning the target in the repository makes a fleet move a reviewed,
revertable one-line change.

## 5. Binding Rules

1. An operation that changes accounts (upgrade, distribution, account
   move, secrets sync, restart) is a signed control-plane action with the
   verification in the reply; when none exists, adding it is the work.
2. An unsigned or wrongly signed action does nothing; an action dated
   more than a minute in the future is refused. The ledger is
   `<fabric state>/agents/<login>/actions-seen.json`.
3. `upgrade claude`: the version is the coordinator's (its pin or
   `--version`) in the signed request; at that version nothing moves.
   Installs queue on the host lease `claude-install` **before** anything is
   stopped (thirteen at once failed nine times, 2026-09-25); a session is
   stopped by SIGTERM only, never SIGKILL — one not stopped in 90 s is a
   failure; the install is `claude install <v>` within 5 minutes, verified
   by `claude --version`, a failure reported by the installer's last line.
   The requester's own session is never stopped.
4. The launcher resumes the stopped session (`--resume <id>`) from the
   restart marker; a failed upgrade still brings it back; a marker older
   than the launch is removed, never obeyed.
5. `upgrade fabric` sends `origin/main`'s sha, never HEAD; an account whose
   fetch lacks it refuses. Fast-forward or nothing: a checkout on a branch
   is refused by name, a `main` that cannot fast-forward fails; neither is
   forced. Bootstrap runs every time, for the provider of the running
   session; no session is stopped; the daemon restarts itself after
   replying.
6. After every merge to the fabric's `main`, the coordinator runs
   `fabric-ctl all upgrade fabric` from a checkout on main; a broadcast is
   not distribution.
7. Any failed row makes `fabric-ctl` exit 1.
8. Every fabric command a session is told to run is listed in
   `runtime/claude-code/commands.json`, in the same change that tells a
   session to run it; `bootstrap.sh` links it into `~/.local/bin`
   (refusing, by name, a file there it did not make) and `user-settings.py`
   writes a narrow `Bash(<name> *)` allow rule. A skill, hook message or
   project snippet names the command, never a path through
   `$AGENT_FABRIC_ROOT` (`tests/test_session_commands.py`).
9. A wrapper that runs another command (`fabric-lease`, `fabric-host`) is
   linked but listed in `not_allowed` with its reason, and still asks. An
   account's own `ask` rule wins over any allow rule.

## 6. Consequences

- One session per login is assumed: the marker and the binding's session
  id are per login.
- The signing key lives in the operator's login (`fabric-ctl keygen`,
  Doppler, `fabric-secrets sync`); it protects the fleet from the relay
  token's other holders, not from the operator's own sessions.
- Hooks are unaffected by the command list: the harness runs them without
  a permission check.

## 7. Future Evolution

Not yet: other pieces (`ori` left for later, the owner, 2026-09-24 — a
piece is an entry in `upgrade.mjs` `PIECES`, not a new op); signed replies
(a forged reply can still show a false row); a restart read back live —
the first upgrade that meets a running session should confirm the
SessionEnd hook ran, the session resumed, and on the broker path that the
launcher's wait returned after the SIGTERM to `claude`.

## 8. Decision Status

Accepted; `upgrade claude` since PR #34/#35/#36 (2026-09-25),
`upgrade fabric` since PR #47 (2026-09-26).

## References

- `bin/fabric-ctl`, `runtime/control/agentd.mjs`, `runtime/control/upgrade.mjs`,
  `bin/fabric-lease`, `bin/fabric-accounts`, `runtime/claude-code/harness.json`.
- `docs/control-plane.md` ("The fence"), `docs/claude-accounts.md`.
- `runtime/claude-code/commands.json`, `runtime/claude-code/bootstrap.sh`,
  `runtime/claude-code/user-settings.py`, `tests/test_session_commands.py`.
- The live checks in Evidence. ADR-008 (the harness pin and user settings).

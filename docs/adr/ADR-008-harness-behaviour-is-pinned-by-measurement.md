# ADR-008 — Harness behaviour is pinned by measurement

**Date:** 2026-09-17
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner (attribution off, 2026-09-18; thinking summaries and verbose, 2026-09-20; fabric commands without approval and auto mode, 2026-09-26); fabric-coordinator (the captures and read-backs)
**Scope:** runtime/claude-code/user-settings.py and the keys it writes into every login's `~/.claude/settings.json`; runtime/claude-code/harness.json (the pinned version); runtime/claude-code/harness/ (the captured harness prompt); how a harness behaviour becomes a fabric rule
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-17-claude-code-harness-prompt.md, docs/live-checks/2026-09-18-attribution-reminder-off.md

## 1. Context and Problem

Claude Code is Anthropic's, and it changes with every build: its system
prompt, the reminders it injects, the settings it honours. Several times
a documented or assumed behaviour turned out different when measured:

- The attribution reminder asking for a `Co-Authored-By:` trailer is
  built by the harness from the `attribution` settings key, injected as a
  `<system-reminder>` on the first turn and after every model switch,
  outside any launch prompt, and only when the session has Bash (read out
  of 2.1.276, 2026-09-18). No fabric prompt carried it.
- `autoUpdates: false` in `~/.claude.json` is not honoured on a native
  install whose `autoUpdatesProtectedForNative` is true (read from 2.1.282):
  the coordinator's account installed 2.1.282 on its own on 2026-09-24.
- The harness's own system prompt has no flag that prints it; it was
  captured from a live session on 2.1.274 (2026-09-17).

## 2. Decision

A harness behaviour the fabric depends on is **measured, not assumed**:
read back live, or read out of the installed binary, with the build and
date as the claim, in `docs/live-checks/`. What the fabric wants on every
agent is then written into **user scope** — the login's
`~/.claude/settings.json`, by `runtime/claude-code/user-settings.py` from
`bootstrap.sh` — because user scope reaches every session whatever
directory it starts in. The keys, and why:

- `attribution` `{commit: "", pr: "", sessionUrl: false}` — the harness
  sends no attribution request (2.1.276 sent the "do not add" form, 2.1.277
  no reminder at all); `sessionUrl` false drops the `Claude-Session:`
  trailer.
- `env.DISABLE_AUTOUPDATER` `"1"` — checked first, unconditionally; it
  stops background updates only, so `claude install <v>` still works. The
  fleet's version is the one `runtime/claude-code/harness.json` pins,
  moved by `fabric-ctl … upgrade claude` and nothing else.
- `showThinkingSummaries` true and `verbose` true
  — an agent's session is read by the person operating the fleet; a
  stalled or misdirected session must be visible from its terminal.
- `permissions.allow` `Bash(<name> *)` for each fabric command, and
  `permissions.defaultMode` `"auto"` — the command
  rule is the fleet-operations record's, which follows; auto mode because eight hand-provisioned
  accounts had no mode and asked for what the classifier would allow.

The harness's system prompt is kept verbatim as
`runtime/claude-code/harness/en.md`, the source a locale translates.

## 3. Alternatives Considered

- **The workspace `.claude/settings.json`.** Rejected: a session starts
  inside its clone and the workspace settings never reach it (learned
  2026-09-16).
- **Carry the keys through the launcher's `--settings`.** Rejected:
  `--settings` is the broker's provider fence.
- **`autoUpdates: false`.** Not the switch on a protected native install
  (above); `DISABLE_UPDATES` would also stop the upgrade's own install.
- **The deprecated `includeCoAuthoredBy`.** Replaced by `attribution`.

## 4. Rationale

The fabric outlives any build of its harness only if what it relies on is
written down with the build it was true of, and re-measured when the build
moves. User-scope keys written on every bootstrap make the wanted
behaviour a property of the account, not of where a session was started.

## 5. Binding Rules

1. A harness behaviour a fabric rule depends on is recorded as a live
   check naming the build and date; a later build is expected to be
   re-read, not assumed.
2. `user-settings.py` writes exactly the fabric's keys, keeps every other
   key as read, prints one line (`+` written, `=` current, `!` refused),
   and refuses any unknown `-` argument rather than take it for the path.
3. Attribution stays off by `attribution` in user scope, and
   `policies/ban_generated_by_attribution.sh` stays at `commit-msg`, in CI
   and in the suite: the switch reaches an account only through a pull and
   a bootstrap, and a stale account still receives the old reminder.
4. Background auto-update is off on every account
   (`env.DISABLE_AUTOUPDATER`); the version moves only by a reviewed
   change to `runtime/claude-code/harness.json` and `fabric-ctl … upgrade
   claude`.
5. `runtime/claude-code/harness/en.md` is the captured text as sent,
   slips included (2.1.274's glued "clickable.Write"), with the memory
   directory as `{memory_dir}`. Refreshing it is a live-check duty on a
   new build; a translation that lags by digest is served and named by
   lint, never a launch failure. The launcher stamps
   `AGENT_FABRIC_LAUNCH_CLAUDE_VERSION` so a build past the capture is
   visible, never a gate.
6. A `-p` probe that disallows tools passes its prompt on stdin:
   `--disallowedTools` is variadic and eats a following positional.

## 6. Consequences

- A `--system-prompt-file` replacement drops the harness text and the
  per-machine Memory section only; tool schemas, listings, CLAUDE.md and
  the reminders stay — which is why the Memory section is in `en.md`.
- Every account's behaviour depends on its last bootstrap; distribution
  after a merge is therefore a duty (ADR-009).

## 7. Future Evolution

The harness text and reminders change with each build; the next capture
is due on a build past `en.md`'s `build`. A read-back on a later build
should expect either attribution outcome of 2.1.276/2.1.277.

## 8. Decision Status

Accepted; keys added 2026-09-18 (attribution), 2026-09-20 (thinking,
verbose), 2026-09-24 (auto-updater), 2026-09-26 (allow rules, auto mode).

## References

- `runtime/claude-code/user-settings.py` (docstring: each key and why),
  `runtime/claude-code/bootstrap.sh`, `runtime/claude-code/harness.json`.
- `runtime/claude-code/harness/README.md`, `runtime/claude-code/harness/en.md`,
  `docs/language-culture-bridge.md`.
- `policies/ban_generated_by_attribution.sh`.
- The live checks in Evidence. ADR-002 (the launch prompt the harness text
  precedes).

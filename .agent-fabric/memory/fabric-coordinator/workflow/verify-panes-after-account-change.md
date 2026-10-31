---
role: "fabric-coordinator"
class: workflow
topic: "verify-panes-after-account-change"
description: "After any account change (fabric-accounts assign, a token sync, a relaunch onto another account), read every affected agent's pane and confirm it is not stuck"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bf62241ee3031280
---

## After any account change (fabric-accounts assign, a token sync, a relaunch onto another account), read every affected agent's pane and confirm it is not stuck

The owner, 2026-10-19, after `fabric-accounts assign all info-gzapi-ge` restarted 14 sessions: "verify the agents
you changed the accounts that are not stucked" and "this should be done everytime you change account settings".

**Why:** a restart onto a new account can leave a session at a login prompt, an API or credit error, or idle with
queued work, and nothing else reports it.

**How to apply:** right after the change:
1. Read the assign table. A `failed` row with "gpg: decryption failed: No secret key" (2026-10-19:
   flutter-dev-02 and p2p-network-dev-02, `fabric-ctl <login> keys` showing signing: no) was NOT a passphrase:
   `gpg --export-secret-keys <key> | sudo -u <login> gpg --batch --import` showed "database_open ... waiting for
   lock (held by <pid>)" with the pid dead, a stale keyboxd lock since the 2026-10-17 restart. The account's own
   agent clears it (its ~/.gnupg); then `provisioning.signing.signing_key(<login>, host)` from my session (my
   agent cached), `fabric-ctl <login> secrets-sync`, and `secrets-selftest` must pass.
2. Run `fabric-ctl all presence`: every restarted login has a session started after the change.
3. Run `agent-fabric-fleetdeck agent list`, then `pane read <id> --source recent --lines 60` for each restarted
   pane. Grep for api error, login, 401/403, rate limit, credit, invalid token. A prompt with a spinner above it is
   working; a bare prompt with queued jobs (python3 open.py over `fabric-ctl all jobs --json`) is stuck. Nudge it
   with `pane send-text` + `send-keys enter` ([[type-into-ssh-pane]], [[stuck-agent-read-its-pane]]).
4. Report to the owner what was checked, per login. Related: [[account-move-needs-relaunch]].

*References: account-move-needs-relaunch, stuck-agent-read-its-pane, type-into-ssh-pane*

*Anchors: `tools/fabric/control/secrets.py::already on it`*

*Observed 2026-10-19 (fabric-coordinator)*

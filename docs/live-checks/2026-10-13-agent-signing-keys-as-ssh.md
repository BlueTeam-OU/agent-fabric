# Live check — agent signing subkeys as SSH signing keys on GitHub (2026-10-13)

**Decides:** ADR-057 — whether one agent key can sign in both formats.

## What was measured

1. Each of the 26 public keys under `identities/keys/` was imported
   into a throwaway GnuPG home. Each has an Ed25519 subkey with signing
   capability only ([S]), beside [E] and [A].
2. `gpg --export-ssh-key '<signing subkey fingerprint>!'` exported each
   one as `ssh-ed25519 …`. All 26 exported, and all 26 are distinct.
3. The 26 were added to the GitHub account that pushes the fleet's
   commits as *signing* keys (`gh ssh-key add --type signing`, after the
   owner granted `admin:ssh_signing_key`). Read back with
   `gh api user/ssh_signing_keys`: 26 titled `fabric-agent <login> (<id>)`.
4. The committer address the fleet uses is verified on that account
   (`gh api user/emails`: `verified: true`).
5. Each agent key's user ids are `<login> <<id>@agents.agent-fabric>`
   and `<login> <<login>@agents.agent-fabric>`, which are not addresses
   on the account. So the same keys as OpenPGP keys would read
   "Unverified" on GitHub.

## What it decides

The signing subkey already serves both formats; no second key is needed
for SSH signing (ADR-057 §3, §4).

## Not verified

No commit has yet been signed with an agent's subkey and pushed.
GitHub's "Verified" verdict on such a commit is expected from its
documented rule, not observed. The first commit `fabric-sign` makes is
that check.

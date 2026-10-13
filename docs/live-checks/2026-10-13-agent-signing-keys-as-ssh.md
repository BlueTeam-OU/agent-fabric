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
5. Every agent key has the user id `<login> <<id>@agents.agent-fabric>`;
   the root key (`user`) also has `<login>@agents.agent-fabric`. Neither
   is an address on the account.

## What it decides

Each agent's signing subkey has an SSH form GitHub accepts as a signing
key, so ADR-057 plans no second key for SSH (§3, §4). That the subkey
signs in that form is checked when `fabric-sign` first does it.

## Not verified

- No SSH signature has been made with an agent's subkey: only its
  public half was exported. Signing through gpg-agent with an [S]-only
  subkey is the first thing `fabric-sign` checks live.
- No commit signed with an agent's subkey has been pushed. GitHub's
  "Verified" for an SSH-signed one, and "Unverified" for the same keys
  as OpenPGP keys (their user ids are not account addresses), are
  expected from GitHub's documented rule, not observed.

# ADR-057 — Each agent signs its own commits, in the format a forge asks for; one key, one timestamp, one checker

**Date:** 2026-10-13
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** how every account signs, timestamps and verifies git commits: the signing command git calls for both OpenPGP and SSH, `policies/signing.json` (which format each forge or repository takes), where timestamp proofs live, the checker run by the hooks and CI (`tools/fabric/guards/ban_unsigned_commits.py` and its successor); the signing subkey of each agent key (ADR-038); ADR-038 §6 "Commits"
**Pillar:** P1
**Evidence:** docs/live-checks/2026-10-13-agent-signing-keys-as-ssh.md

## 1. Context and Problem

Every commit the fleet makes is signed, and by one key: the 60 latest
non-merge commits on main carry the owner's OpenPGP key, whichever role
made them (fabric-coordinator 37, python-dev 19, devex-tooling 4).
Cryptographically the fleet is one signer; which agent made a commit is
said only by its `Fabric-Role:` trailer, text any account can write.
ADR-038 gave each login its own key, certified along its lineage, with
a signing subkey nothing uses yet, and said the shared key must go
(§6 "Commits"), leaving per-agent signing to its own record.

Two forges pull in different directions. GitHub verifies an OpenPGP
signature only when the key carries an e-mail address verified on the
account, which an agent key (`<id>@agents.agent-fabric`) does not, and
the fleet commits under one author; an SSH signing key carries no
address, so GitHub verifies it against the committer's. Radicle, the
forge being explored, may want either. Timestamping is built today into
the OpenPGP path (`ots-git-gpg-wrapper` embeds the proof in the
signature), and an SSH signature has no room for it.

## 2. Decision

Each agent signs its commits with its own signing subkey. One command,
`fabric-sign`, is git's signing program for both formats: it signs
OpenPGP or SSH with that same Ed25519 subkey, as `policies/signing.json`
says for the repository's forge, and timestamps every signature the same
way, its proof kept in git notes. One checker, in the hooks and in CI,
accepts either format, traces the key to its agent through the
committed lineage and checks the proof and the role. Changing a forge's
format is a policy line, never a new key.

## 3. Alternatives Considered

- **Keep the shared key.** One signer for the fleet: a commit's agent
  stays an unverified claim, and the owner's key signs work the owner
  did not review. ADR-038 already rejected it.
- **Per-agent OpenPGP only.** Keeps today's timestamp wrapper, but
  GitHub shows every agent commit "Unverified" unless each agent key
  carries the owner's address, which would make an agent key claim the
  owner's identity.
- **Per-agent SSH only.** Verified on GitHub today, but closes the door
  on a forge or a reader that wants OpenPGP; the format would be decided
  again in code the next time a forge differs.
- **A separate SSH key per agent for signing.** A second key with its
  own lineage and backup, where the signing subkey already serves both
  formats (the live check).

## 4. Rationale

The agent key is the identity (ADR-038), and its signing subkey is an
Ed25519 key that OpenPGP and SSH both use: one key, two encodings, so
the format is a property of the forge and not of the agent. Taking the
timestamp out of the signature makes it format-independent and gives one
checker one rule. The cost is that a proof is a separate ref a clone must
fetch, accepted because CI, not a reader's clone, is where proofs are
judged.

## 5. Binding Rules

1. Each account signs its commits with the signing subkey of its own
   agent key (ADR-038 §5 rule 1), never another account's and never the
   shared key. A commit made before rule 1 holds for its account keeps
   the signature it has.
2. `fabric-sign` is git's signing program for both formats
   (`gpg.program` and `gpg.ssh.program`); it signs with the subkey in
   the format git asks for, and fails, never signs without a timestamp
   request having succeeded (the wrapper's rule today, kept).
3. Which format a working copy signs in is `policies/signing.json`, by
   forge or by repository, `openpgp` or `ssh`; bootstrap writes the git
   settings it implies (`gpg.format`, `user.signingkey`). No other
   place sets the format.
4. Every signature is timestamped with OpenTimestamps, its proof stored
   as a git note on the commit under `refs/notes/fabric-ots`, which
   the pre-push hook pushes with the branch.
5. The checker refuses a commit a branch adds unless: it is signed in a
   format the policy admits for that repository; the key is the signing
   subkey of an agent key under `identities/keys/`, certified along the
   lineage to the root; that agent holds, by `policies/authority.json`,
   the role its `Fabric-Role:` trailer names; and its timestamp proof
   is present and matches the signature. It runs in the commit hooks, in
   CI on every commit a branch adds, and in `tests/run.sh`.
6. The SSH form of every agent's signing subkey is registered as a
   signing key on the GitHub account that pushes the fleet's commits,
   titled `fabric-agent <login> (<id>)`; a new agent's is added at
   provisioning, a revoked one's removed.
7. The git author stays the one shared author (ADR-056 §5 rule 8); the
   signature, not the author, names the agent.

## 6. Consequences

- GitHub shows each agent's commits "Verified", and the lane a commit
  claims is checked against the key that signed it.
- The owner's key stops signing the fleet's work.
- A proof travels as a note: a clone without `refs/notes/fabric-ots`
  has signed commits without their timestamps; CI has both.
- The signing command, the checker and the hooks are new code
  (python-dev), installed on every account by the usual upgrade.

## 7. Future Evolution

- Radicle's own identity key: whether an agent's Radicle node key is
  this signing subkey, so an agent is one identity on every forge, or a
  separate key as ADR-038 says, is decided by the Radicle spike.
- Proofs upgraded to Bitcoin attestations once confirmed, if the owner
  wants them (`--no-bitcoin` today).

## 8. Decision Status

Proposed. The owner asked for a general signing system in both formats,
an agent's own key for each, and timestamping kept. Accepting it
amends ADR-038 §6 "Commits", which waits on it.

## References

- ADR-038 (agent keys, lineage), ADR-039 (agent id), ADR-056 §5 rule 8
  (authorship stays).
- `tools/fabric/guards/ban_unsigned_commits.py`, `identities/keys/`.

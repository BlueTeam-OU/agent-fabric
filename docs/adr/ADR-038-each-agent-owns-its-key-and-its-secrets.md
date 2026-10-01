# ADR-038 — Each agent owns its key and its secrets

**Date:** 2026-09-29
**Status:** Accepted
**Ratified:** owner, 2026-09-29, by the merge of agent-fabric #63 (e00f750)
**Decision Makers:** the owner (the move off Doppler, a repository per agent, a key per agent, paper recovery, the parent's role, no assumed co-location); drafted by fabric-coordinator
**Scope:** every agent's credentials and the key that guards them: `tools/fabric/secret_store.py` behind `bin/fabric-secrets`; each agent's repository `gzapi-org/agent-fabric-secrets-<id>` (ADR-039); `identities/keys/`; `~/.config/agent-fabric/secrets.env` and its consumers; filling a child's store (`fabric-secrets provision`); the migration from Doppler (ADR-012), complete; the Claude-account templates (ADR-031); provisioning (`runtime/provisioning/new-agent.sh`)
**Pillar:** P1

## 1. Context and Problem

An agent's secrets live in a third-party service: one Doppler config
per login, read with a service token that the account holds in plain.
The record of who holds what is the service's. Its backup is the
service's too. Moving the fleet to a host without the vendor's CLI means
moving the vendor.

The owner keeps personal secrets in a portable form instead: a git
repository of GPG-encrypted entries, opened with QtPass and browserpass.
With that form, the only thing left to back up is a key.

The fabric's invariant says who an agent is: its Linux login. Nothing
says what a key is to that identity. The gap is already visible. Every
account signs its git commits with the same key, the coordinator's,
imported by hand at provisioning. Cryptographically, the fleet is one
signer.

## 2. Decision

Each agent owns one key and one encrypted store, and the fabric's theory
of identity is extended to keys.

- **The login is the principal, and the key is its credential.** Never
  the reverse.
- **A key is an agent's when it is attested by lineage.** Its public half
  is committed under the agent's login, and it is certified by its
  parent, the coordinator that provisioned it.
- **An agent's secrets are readable by that login alone.** Anyone
  holding the committed public key can write into the store, so the
  parent supplies secrets without being able to read them.
- **Recovery is the owner's, one encrypted copy per agent,** opened only
  with the owner's recovery passphrase.
- **Rotation keeps the identity.** Retirement leaves no heir.
- **Placement is neither identity nor an assumption.** Agents may live
  on different hosts, and nothing here depends on their sharing one.
- **Authority stays apart from identity.**

The store is a private repository per agent, `gzapi-org/agent-fabric-secrets-<id>`
(the agent id, ADR-039),
in the layout pass(1) uses:
- a `.gpg-id` naming the key;
- one `env/<NAME>.gpg` per secret, the value on the first line.

`fabric-secrets sync` reads it and writes the same
`~/.config/agent-fabric/secrets.env` as before. So every consumer is
unchanged, and only the source moves.

## 3. Alternatives Considered

- **Keep Doppler.** The owner decided to leave it: a vendor holds the
  record and its backup, and the fleet's portability is the vendor's.
- **One repository for every agent, a folder each.** Every agent would
  clone every other agent's ciphertext and its history, and one agent's
  mistake would sit in the others' log.
- **A human master key as a recipient on every store.** One key would
  read the whole fleet, so losing it would expose everything. The owner
  chose a key per agent, each the sole reader of its own store.
- **Shares of a key held by other agents.** Accounts that share a host
  fail together: one compromise, or one lost disk, takes every share.
  Paper fails independently of any host.
- **age or sops instead of GPG.** Neither opens in QtPass or browserpass.
  GPG is already a required host tool for signing.

## 4. Rationale

The design reuses a standard format the owner already uses, so any
agent's store opens with the owner's own tools once its recovered key is
imported. It changes one seam: `secrets.env` stays the interface, so the
launcher, the inbox, the control agent, the MCP server and the shell
read what they read today.

It also makes custody follow the lane rule. An agent reads only its
own secrets. The parent writes, and is never able to read. The owner
recovers with the recovery passphrase, one agent at a time.

It survives the loss of a host. The ciphertext lives on GitHub and at
the parent, and the key's copy lives in Proton, encrypted to the owner's recovery key. Nothing depends on the agents'
sharing a machine.

## 5. Binding Rules

1. Each login has exactly one agent key, generated inside that account:
   a primary that only certifies, the agent's identity, and beneath it
   one subkey per use, encryption (the store), signing and
   authentication, so each use can be rotated alone and a leaked one
   opens nothing else. A key made before the split keeps its
   fingerprint and gains the subkeys it lacks (A 2026-09-29).
   Its private half leaves the account only as that agent's recovery copy:
   the paperkey text and revocation certificate, encrypted by the account
   to the owner's recovery key (`identities/recovery.asc`) and carried to
   the fleet's Proton Drive by the parent's backup. The recovery key's
   private half is protected by a passphrase only the owner knows and is
   kept only in Proton; no agent can read any recovery copy, its own
   included. A key held anywhere else is a stolen credential and is
   revoked (A 2026-09-29).
2. A key is an agent's only when both hold:
   - its public half is committed at `identities/keys/<id>.asc`, the
     agent's id (ADR-039);
   - the committed key carries a certification by the key of the parent
     recorded for that id in `identities/keys/lineage.json`
     (A 2026-09-29).
   The coordinator's own key is the root of the chain, committed the
   same way and recorded with no parent. Lint refuses a committed key
   without its parent's certification.
3. An agent's store is encrypted to that agent's key alone (`.gpg-id`).
   Any holder of the committed public key may add an entry (`fabric-secrets
   put`); its parent fills a new agent's store that way (`fabric-secrets
   provision`: identity, an allowlist of shared names, a key of its own on
   each API) (A 2026-09-30). Only the agent decrypts. No store is
   encrypted to another agent's key.
4. A key names no host. A login moved with its home keeps its key. A
   login rebuilt without its home is re-keyed: its new key is certified
   by its parent, and the old key is revoked.
5. No step between agents relies on a shared host or on crossing
   accounts:
   - certification travels through the agent-fabric repository;
   - `put` is a push to the child's repository;
   - sync is a signed control action (ADR-029);
   - a new account, which has no GitHub key until its first sync writes
     one, meets its store through its parent: its first commit as an
     armored git bundle the parent pushes (`store bundle | store
     seed-child`, store-enroll.sh `--born-now`), and its filled store back
     the same way before that sync (`store child-bundle | store
     take-bundle`, then `sync --no-pull`). A bundle carries only
     ciphertext, the key's fingerprint and the agent id, through the host
     executor's stdin and stdout; the child takes one only of its own store
     (A 2026-10-01).
6. Each key's recovery copy is written once at birth
   (`fabric-secrets store recovery-copy`), encrypted before it leaves the
   process and printing only a path, so it may run inside a model
   session. The recovery key is made by the owner in a terminal
   (`recovery-key init`, which asks for the passphrase). The paths that
   print a copy in the clear (`paper`, `paper --out`) refuse inside a
   model session (`CLAUDECODE` set). No secret value is ever shown to a
   model, put in a message, or written to a log (A 2026-09-29).
7. `fabric-secrets sync` reads the store alone; its exit codes are
   (A 2026-09-30):
   - 0: applied;
   - 1: unreadable;
   - 2: applied, with required names missing;
   - 3: the store names another login, and nothing is applied.
8. Every account reads its own store; Doppler is removed from the code —
   its reader, `import-doppler`, the migration action, the enrolment and
   the Doppler templates — and nothing reads a source file. The migration
   compared the sha256 of every value sync applies (`values_sha256`),
   never a value, before and after each account's switch
   (A 2026-09-30).

## 6. Consequences

- **What the owner keeps:** the recovery passphrase, and a dedicated
  Proton account for the fleet, with 2FA and its recovery phrase. The
  account holds every store's backup (`fabric-secrets store backup`,
  bundles with a sha256 manifest, checked by `--verify`), every agent's
  recovery copy and the protected recovery key; it is shared read-only
  with the owner's own account. Reading a recovery copy needs both the
  account and the passphrase, so neither alone opens the fleet. The owner's own
  Proton account is never signed in on the agents' host. Opening a store
  needs its recovery copy and a GPG tool: `pass`, QtPass or browserpass.
- **The Proton session** is an entry of the backing-up login's own
  store (`PROTON_DRIVE_CREDENTIALS_STORE=pass`), readable by that login
  alone; `proton-drive auth login` is the owner's, in a browser.
- **What leaks:** entry names are visible to whoever can read the
  private repository. Values are not.
- **Key storage:** an agent's key has no passphrase, because agents
  decrypt unattended. The account's file permissions guard it, the same
  protection `secrets.env` has.
- **Commits:** the shared signing key stays until per-agent signing
  lands. Rule 1 says it must go.

## 7. Future Evolution

- **Per-agent git signing** with the agent's signing subkey, replacing
  the shared coordinator key; its own record, since it changes the
  fleet's commits. **The authentication subkey as each agent's SSH key**
  through gpg-agent, replacing the shared one, likewise.
- **The identity key off the host:** only its subkeys kept online, the
  primary only in the recovery copy, once certifying no longer needs it
  there (the coordinator certifies children with its own).
- **Doppler off the hosts:** each account's `~/.doppler` goes with the
  upgrade that distributes its removal (`bootstrap.sh`); a token kept in
  a desktop keyring stays there until the project is closed; the binary
  under `/usr/local` is each host operator's to remove, and the project,
  which revokes every token, the owner's to close.
- **Hardware-held keys,** if an agent's host offers one.

## 8. Decision Status

Accepted and in force. Every account reads its own store; a new account
is keyed by `store-enroll.sh` and filled by `fabric-secrets provision`.

## References

- ADR-012 — credentials; the Doppler layout this replaced.
- ADR-031 — the Claude-account templates, which move to the coordinator's store.
- ADR-029 — the signed control actions that carry sync.
- ADR-003 — per-agent state, which a moved login carries.

## Amendments

The body above reads current; each change's full note is in [history/ADR-038-amendments.md](history/ADR-038-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-29 | The recovery copy and the backup go to Proton Drive | §5 rules 1 and 6, §6: Proton instead of paper; the backup |
| 2026-09-29 | Recovery copies are encrypted to the owner's recovery key | §5 rules 1 and 6, §6: option B, the passphrase-protected recovery key |
| 2026-09-29 | Keys and stores are named by the agent id | §2, §5 rule 2, Scope: `<id>.asc`, `agent-fabric-secrets-<id>` (ADR-039) |
| 2026-09-29 | One identity key per agent, a key per use beneath it | §5 rule 1, §7: a certify-only primary with encryption, signing and authentication subkeys |
| 2026-09-30 | Doppler is removed: every account reads its own store, and a parent fills a child's with provision | Scope, §5 rules 3, 5, 7, 8; §7; §8 |
| 2026-10-01 | A new account's store reaches it as a bundle | §5 rule 5: the first commit and the filled store travel as bundles through the parent; `sync --no-pull` once |

# ADR-042 — Store commits are signed by their writer and verified before they are applied

**Date:** 2026-10-04
**Status:** Accepted
**Ratified:** owner, 2026-10-04, by the merge of agent-fabric #91 (a05c9cab), which carried it, as §8 provided
**Decision Makers:** the owner (signed and verified, over trusting repository access); drafted by fabric-coordinator
**Scope:** `tools/fabric/secret_store.py` (every commit to an agent's store, `pull`, `take-bundle`, `seed-child`, `sync`), `identities/keys/lineage.json` as the record of who may write a store, and the per-agent store repositories `agent-fabric-secrets-<id>`
**Pillar:** P1

## 1. Context and Problem

ADR-038 gives each agent a private store of its secrets, a pass(1)
repository encrypted to that agent's key alone. Two parties write it: the
agent itself (`fabric-secrets set`) and its parent (`put`, `seed-child`).
What the store checks when it takes a commit in is the store's identity:
the agent id, and the key the entries are encrypted to. It does not check
who wrote the commit. `_commit` turns signing off, and `pull`,
`take-bundle` and the fast-forward before a push take any commit the
remote or a bundle carries.

So anyone who can push to an agent's store repository, or hand it a
bundle, can add entries encrypted to that agent's public key, and the
agent's next `sync` applies them. A public key is public. An entry is a
credential the agent will use: a token, an SSH key, a provider key. A
forged one points the agent at an account or a relay it was never meant to
use, and nothing would say so. The review of #76 named this as a carried
risk. #90's review saw the same trust extended when a push began
fast-forwarding to the remote.

## 2. Decision

Every commit to an agent's store is signed with its writer's own key. A
store applies only commits signed by a key allowed to write it: the
agent's own key, or its recorded parent's. Anything else is refused,
named, and never applied. The history each store already holds, unsigned,
is trusted once, at a recorded commit; verification starts after it.

## 3. Alternatives Considered

- **Repository access as the control.** Trust whoever can push, and make
  GitHub's access the boundary. Rejected: the store would then be as safe
  as the most exposed token that can write it. The fabric already holds
  several such tokens, and a store's whole purpose (ADR-038) is that only
  its owner and its parent can put a secret into it.
- **Signed tags or a signed manifest per sync.** One signature over a
  state rather than over each commit. Rejected: a forged commit between
  two signed states is applied before anything checks it, and the parent's
  and the agent's writes interleave.
- **Verifying only at `sync`, not at `pull`.** Rejected: the mirror would
  hold forged commits, and the next write, which rebases onto them, would
  sign over them.

## 4. Rationale

The keys exist already. Since ADR-038, every account holds a signing
subkey under its primary key. The primary key is committed at
`identities/keys/<id>.asc` and recorded, with its parent, in
`lineage.json`. So signing costs nothing new to provision, and
verification needs no authority beyond what the fabric already commits. A per-commit check
refuses a forged entry before it reaches the store, rather than finding it
after it has been applied. The cost is one signature per write and one
verification per pull: a few hundred milliseconds on a store that changes
a handful of times a day.

## 5. Binding Rules

1. A commit to an agent's store is signed with its writer's signing
   subkey: the agent's own for `set`, the parent's for `put` and
   `seed-child`. A writer that cannot sign does not write.
2. The keys allowed to write a store are the agent's own and its
   parent's, as `identities/keys/lineage.json` records them on the
   fabric's main branch: a commit verifies when it is signed by a signing
   subkey of one of those primary keys, read from the committed
   `identities/keys/<id>.asc`. Both files are read as the account's
   fabric checkout has them at `origin/main`, never from its working
   tree, so an uncommitted edit names nobody; a key not there yet is
   refused with a pointer to fetch the fabric. The root agent, which has
   no parent, is its own store's only writer. Nothing else names a
   writer.
3. `pull`, `take-bundle`, the fast-forward before a push, and `sync`
   verify every commit they would take beyond the store's trusted base. A
   commit unsigned, signed by a key outside rule 2, or failing
   verification refuses the whole operation: nothing is applied, and the
   refusal names the commit and the reason, never an entry's value.
4. Each store records its trusted base: the commit up to which history
   is taken unsigned, in the store's own git configuration, never in a
   commit the remote could write. It is set explicitly, never inferred
   from a store that has none: `fabric-secrets store trust-base`, which
   bootstrap runs once per account for every store it then holds (the
   migration). A store born later gets its base at first contact, from
   the enrolment bundle the host executor carries, never from a fetch:
   the parent's mirror at `seed-child`, the child's store at its first
   `take-bundle` while the agent is not yet on main's lineage. A store
   with no base refuses every verified operation and names the command.
   The base only ever moves forward, to a verified commit.
5. A refusal is a security event. `fabric-secrets status` and
   `fabric-ctl <login> keys` say it until the store is repaired, and the
   repair is the parent's or the owner's. A commit that verification
   could not judge is not refused but stops the operation: "could not be
   verified; nothing applied", nothing recorded. It is one that gave not a
   single [GNUPG:] status line while it carries the signature header git
   verifies for the store's object format (gpgsig for sha1, gpgsig-sha256
   for sha256) with PGP armour in it: there the machine failed (no gpg, an
   unusable temporary directory), not the commit. Any other commit that
   does not verify, a header of the wrong format or junk in armour
   included, is refused "not signed" and recorded, so push access to a
   store's remote cannot turn a refusal into a silent stop (A 2026-10-07).

## 6. Consequences

- A forged entry can no longer reach an agent through its store. To forge
  one, an attacker now needs a writer's private key, not just push access.
- Every store write needs its writer's signing key unlocked. That is
  already true of the encryption it does.
- A rotated signing subkey verifies once the agent's committed
  `identities/keys/<id>.asc` carries it on main. A new primary key also
  reaches `lineage.json`. Rotation already goes through both.
- One migration: each store's current head becomes its trusted base, and
  each account's signing configuration for the store is set.

## 7. Future Evolution

The coordinator as a third writer, for fleet-wide changes, would be a
`lineage.json` rule, not a change here. If GitHub's own commit
verification ever reads these keys, the verification could move to the
server side; it would add to the local check, not replace it.

## 8. Decision Status

Accepted and in force: `secret_store.py` signs every store write and
verifies before it takes, and bootstrap's last step sets each existing
store's trusted base once.

## References

- `tools/fabric/secret_store.py`: `_commit`, `_before_write`, `pull`,
  `seed_child`, `take_bundle`, `put`, `set_entry`; `identities/keys/lineage.json`.
- ADR-038 (each agent owns its key and its secrets), ADR-039 (the agent
  id), ADR-012 (credentials).

## Amendments

The body above reads current; each change's full note is in [history/ADR-042-amendments.md](history/ADR-042-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-04 | Where writers are read; how a base is set | §5 rules 2 and 4: writers from origin/main, never the working tree; the base explicit, by a once-only migration or at first contact through the enrolment bundle |
| 2026-10-07 | A commit verification could not judge is a stop, not a refusal | §5 rule 5: no [GNUPG:] status, the store format's signature header with PGP armour: stop, nothing applied, nothing recorded; every other unverified commit refused as before |

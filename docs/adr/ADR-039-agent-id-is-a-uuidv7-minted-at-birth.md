# ADR-039 — The agent id is a UUIDv7 minted at birth

**Date:** 2026-09-29
**Status:** Proposed
**Decision Makers:** the owner (an id per agent from its birth time; the id as the identity across renames; the birth of an existing agent as its home's creation time, of a new one as its enrolment; what is stored named by the id, what is typed and read named by the login, the repository's description carrying both); drafted by fabric-coordinator
**Scope:** the agent's identity record: `identities/keys/lineage.json` and `identities/keys/<id>.asc`; the agent key's user id; each agent's secrets repository and its mirror, bundle and recovery copy (ADR-038); `tools/fabric/secret_store.py`, `runtime/provisioning/secrets/store-enroll.sh`, `runtime/provisioning/new-agent.sh`
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-29-coordinator-secrets-migration.md

## 1. Context and Problem

The fabric's invariant makes the Linux login the agent. The login is also
a name, and a name can change. Everything ADR-038 created was keyed by it:
- the secrets repository `secrets-<login>`;
- the committed key `identities/keys/<login>.asc`;
- the lineage entry, and the parent a child names;
- the key's user id, `<login>@agents.agent-fabric`.

A renamed login would break each of them. A login name reused after its
agent retired would look like its predecessor to every one of them. That
contradicts ADR-038's "death has no heir".

## 2. Decision

Each agent has an **agent id**: a UUIDv7 whose timestamp is the agent's
birth, minted once by its parent and recorded. The id identifies the
agent across renames; the login is its current name on its host.

- **Birth.** An existing account's birth is its home directory's creation
  time, read on its own host. A new account's birth is its enrolment
  (`new-agent.sh`).
- **What is stored is named by the id:**
  - the lineage entry;
  - the committed key file;
  - the key's user id address;
  - the secrets repository `agent-fabric-secrets-<id>`;
  - the parent's mirror;
  - the backup bundle;
  - the recovery copy.
- **What a person types and reads is the login.** Every command takes a
  login (or an id), resolves it to the id through `lineage.json` first,
  and works with the id from then on. Each repository's description
  gives both: `Linux login: <login>. Agent id: <id>.`
- **A rename** changes the lineage entry's `login` and the repository's
  description. Nothing stored moves.

The invariant stands at runtime: the login this session runs as is who it
is, and `fabric-whoami` answers with it. The id is what that login is
recorded as, and it outlives any one name.

## 3. Alternatives Considered

- **Keep the login as the key.** Every record breaks on a rename. A reused
  name inherits its predecessor's records.
- **A UUIDv4, or a counter.** A counter needs a central allocator, and a
  v4 id carries nothing. A v7 id sorts by birth and states it, and its
  random bits still make two agents born in the same millisecond distinct.
- **Logins as the stored names, the id beneath.** Readable in a
  directory listing, but a rename then moves the key file, the
  repository and every mirror, and an outage in the middle leaves them
  disagreeing. With the id as the stored name, a rename touches one
  field and a description.
- **An id derived from the key's fingerprint.** It changes on every
  rotation, which ADR-038 rule 4 says keeps the identity.
- **The UID number of the account.** It belongs to the host, and it
  differs across hosts; ADR-038 rule 7 forbids placement as identity.

## 4. Rationale

The id carries its own birth, so it needs no second record to be dated,
and `verify` can check that the recorded birth is the id's.

Minting once, rather than deriving, keeps the id stable when the evidence
of birth moves: a home copied to a new disk gets a new creation time but
keeps the recorded id.

Keying the records by the id makes a rename a one-field edit, with no
file or repository renamed. Naming the parent by its id keeps the chain
whole when the parent is renamed.

## 5. Binding Rules

1. An agent's id is a UUIDv7. Its timestamp is the agent's birth:
   - for an account enrolled after it was made, its home directory's
     creation time on its own host;
   - for an account made by `new-agent.sh`, the moment of its enrolment.

   It is minted once, by the parent, and recorded; it is never recomputed
   and never replaced.
2. `identities/keys/lineage.json` is keyed by agent id. Each entry holds:
   - `login`, unique among the agents;
   - `born`, equal to the id's time;
   - `fingerprint`;
   - `parent`, the parent's agent id, or null for the root.

   The committed key is `identities/keys/<id>.asc`.
3. An agent key carries a valid user id addressed to
   `<id>@agents.agent-fabric`. The parent's certification is on that user
   id. `verify` and lint refuse a key without either.
4. An agent's secrets repository is `<org>/agent-fabric-secrets-<id>`.
   The parent's mirror is `children/<id>`. The backup bundle is
   `agent-fabric-secrets-<id>.bundle`. The recovery copy is
   `recovery/<id>.key.gpg`.
5. A command that names an agent takes its login or its id and resolves
   it through `lineage.json` before anything else; below that point only
   the id is used. A repository's description gives the Linux login and
   the agent id.
6. A rename (`store-enroll.sh --rename <old> <new>`) changes the entry's
   `login` and the repository's description, and nothing else.
7. A login reused after its agent retired is a new agent with a new id.
   Certifying a second agent under a login that a recorded agent holds is
   refused.

## 6. Consequences

- **Readability.** Repository and file names are ids. Commands and
  output use logins, and each repository's description gives both, so a
  person reading the GitHub list sees whose store it is.
- **The key's name part** is the login at birth, a label. The address is
  what identifies the agent.
- **What still keys by login:**
  - the GZCoord address `<host>/<login>`, because the protocol's grammar
    is frozen;
  - the runtime state directories;
  - the parent's `CLAUDE_ASSIGNED_<LOGIN>` records.

  A rename leaves these to follow, and they are listed for the procedure
  that renames an account.
- **The coordinator** was migrated in place: same key, a new user id, and
  its repository renamed on GitHub.

## 7. Future Evolution

- **A rename procedure:** the Linux account, the runtime state, the relay
  address and the lineage, in one step.
- **`fabric-whoami --json` printing the agent id** beside the login.
- **Retirement recorded in the lineage,** so that a reused login's second
  agent can be certified.

## 8. Decision Status

Proposed with the rollout of ADR-038. It is accepted by the owner's merge
of the pull request that carries it. The coordinator already holds its
id; every other agent receives one at enrolment.

## References

- ADR-038 — each agent owns its key and its secrets; this record keys them by id.
- ADR-003 — per-agent state, which a moved login carries.
- `tools/fabric/secret_store.py` (`mint_agent_id`, `verify`, `rename`); `runtime/provisioning/secrets/store-enroll.sh`.
- `tests/test_secret_store.py`, `runtime/provisioning/secrets/test_store-enroll.sh`.

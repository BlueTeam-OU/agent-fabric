# ADR-039 — The agent id is a UUIDv7 minted at birth

**Date:** 2026-09-29
**Status:** Proposed
**Decision Makers:** the owner (an id per agent from its birth time; the id as the identity across renames; the birth of an existing agent as its home's creation time, of a new one as its enrolment; names, not ids, wherever a person reads them, with the id recorded underneath; the repository name `agent-fabric-secrets-<login>`); drafted by fabric-coordinator
**Scope:** the agent's identity record: `identities/keys/lineage.json` and `identities/keys/<login>.asc`; the agent key's user id; each agent's secrets repository and its mirror, bundle and recovery copy (ADR-038); `tools/fabric/secret_store.py`, `runtime/provisioning/secrets/store-enroll.sh`, `runtime/provisioning/new-agent.sh`
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-29-coordinator-secrets-migration.md

## 1. Context and Problem

The fabric's invariant makes the Linux login the agent. The login is also
a name, and a name can change. Everything ADR-038 created was keyed by it:
- the secrets repository `secrets-<login>`;
- the committed key `identities/keys/<login>.asc`;
- the lineage entry, and the parent a child names;
- the key's user id, `<login>@agents.agent-fabric`.

A renamed login would break each of them, and nothing would say it was
the same agent. A login name reused after its agent retired would look
like its predecessor to every one of them. That contradicts ADR-038's
"death has no heir".

## 2. Decision

Each agent has an **agent id**: a UUIDv7 whose timestamp is the agent's
birth, minted once by its parent and recorded. The id identifies the
agent across renames; the login is its current name on its host.

- **Birth.** An existing account's birth is its home directory's creation
  time, read on its own host. A new account's birth is its enrolment
  (`new-agent.sh`).
- **Names stay names.** Everything a person reads is named by the login:
  - the lineage entry;
  - the committed key file `<login>.asc`;
  - the secrets repository `agent-fabric-secrets-<login>`;
  - the parent's mirror, the backup bundle and the recovery copy.
- **The id is recorded underneath:**
  - in the lineage entry, as `agent_id`;
  - as the address of the key's user id;
  - in the store's `.agent-id`.

  A parent is named by its id, so the lineage is the table that
  translates a name to the agent.
- **A rename** moves the name: the entry, the key file, the repository
  and the mirror (`store-enroll.sh --rename`). The id and the key stay.

The invariant stands at runtime: the login this session runs as is who it
is, and `fabric-whoami` answers with it. The id is what that login is
recorded as, and it outlives any one name.

## 3. Alternatives Considered

- **The login with nothing beneath it.** Nothing says a renamed login is
  the same agent, and a reused name inherits its predecessor's records.
- **A UUIDv4, or a counter.** A counter needs a central allocator, and a
  v4 id carries nothing. A v7 id sorts by birth and states it, and its
  random bits still make two agents born in the same millisecond distinct.
- **The id as every name** (repository, files, mirrors). It makes a
  rename a one-field edit, but a person reading the repository list or
  the key directory sees only ids.
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

Names stay readable where people read them, and the id underneath is
what proves a renamed agent is the same agent. A rename costs a few
moves, which one command makes. Naming the parent by its id keeps the
chain whole when the parent is renamed.

## 5. Binding Rules

1. An agent's id is a UUIDv7. Its timestamp is the agent's birth:
   - for an account enrolled after it was made, its home directory's
     creation time on its own host;
   - for an account made by `new-agent.sh`, the moment of its enrolment.

   It is minted once, by the parent, and recorded; it is never recomputed
   and never replaced.
2. `identities/keys/lineage.json` is keyed by login. Each entry holds:
   - `agent_id`, unique among the agents;
   - `born`, equal to the id's time;
   - `fingerprint`;
   - `parent`, the parent's agent id, or null for the root.

   The committed key is `identities/keys/<login>.asc`.
3. An agent key carries a valid user id addressed to
   `<id>@agents.agent-fabric`. The parent's certification is on that user
   id. `verify` and lint refuse a key without either.
4. An agent's secrets repository is `<org>/agent-fabric-secrets-<login>`.
   The parent's mirror is `children/<login>`. The backup bundle is
   `agent-fabric-secrets-<login>.bundle`. The recovery copy is
   `recovery/<login>.key.gpg`.
5. A rename moves the name and keeps the id and the key:
   `store-enroll.sh --rename <old> <new>` renames the lineage entry, the
   key file, the repository and the parent's mirror.
6. A login reused after its agent retired is a new agent with a new id.
   Certifying a second agent under a login that a recorded agent holds is
   refused.

## 6. Consequences

- **Readability.** Names are logins. The id is in the lineage, in each
  repository's description and in the key.
- **The key's name part** is the login at birth, a label. The address is
  what identifies the agent, and a rename does not touch the key.
- **What still keys by login:**
  - the GZCoord address `<host>/<login>`, because the protocol's grammar
    is frozen;
  - the runtime state directories;
  - the parent's `CLAUDE_ASSIGNED_<LOGIN>` records.

  `--rename` leaves these, with the Linux account itself, to the procedure
  that renames an account on its host.
- **The coordinator** was migrated in place: same key, a new user id,
  and its repository renamed on GitHub to `agent-fabric-secrets-user`.

## 7. Future Evolution

- **A whole-account rename:** the Linux account, the runtime state and
  the relay address together with `--rename`, in one step.
- **`fabric-whoami --json` printing the agent id** beside the login.
- **Retirement recorded in the lineage,** so that a reused login's second
  agent can be certified.

## 8. Decision Status

Proposed with the rollout of ADR-038. It is accepted by the owner's merge
of the pull request that carries it. The coordinator already holds its
id; every other agent receives one at enrolment.

## References

- ADR-038 — each agent owns its key and its secrets; this record gives each an id beneath its name.
- ADR-003 — per-agent state, which a moved login carries.
- `tools/fabric/secret_store.py` (`mint_agent_id`, `verify`, `rename`); `runtime/provisioning/secrets/store-enroll.sh`.
- `tests/test_secret_store.py`, `runtime/provisioning/secrets/test_store-enroll.sh`.

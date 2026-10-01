---
role: "fabric-coordinator"
class: rationale
description: "owner 2026-09-29 — each agent gets a UUIDv7 id minted from its birth; the id is the identity across renames, the login its current name; secrets repos are agent-fabric-secrets-<id>"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c43a55417dfff30c
---

## owner 2026-09-29 — each agent gets a UUIDv7 id minted from its birth; the id is the identity across renames, the login its current name; secrets repos are agent-fabric-secrets-<id>

Decided by the owner on 2026-09-29, to keep a renamed agent the same agent:

- **The id.** Each agent gets a UUIDv7 whose timestamp is its birth. It is minted once and recorded; it is never recomputed.
- **Birth.** An existing agent's birth is its home directory's creation time. A future agent's birth is its enrolment time.
- **Scope ("Id is the identity").** The id is the agent's identity across renames, and the login is its current name. It is recorded in `identities/keys/lineage.json` and used in the key's user id. The secrets repositories were first named `agent-fabric-secrets-<id>`; that was superseded the same day (below).
- **What stays.** The GZCoord address stays `host/login`, because the protocol is frozen.

**Why:** renaming a login used to break everything keyed by the name. A reused name after retirement also looked like its predecessor, which ADR-038's "death has no heir" forbids.

**How to apply:** a new ADR amends the invariant, "the login names the agent, the id identifies it". Land it before the fleet is enrolled, so only the coordinator's own store (`gzapi-org/secrets-user`) has to be renamed. [[agent-owned-secrets-plan]]


Revised the same day. The owner rejected ids everywhere: "I don't want to use the UUID everywhere, I could use the current name like architect-cto-01 and then translated".

- **Names stay logins:** the lineage key, `<login>.asc`, `agent-fabric-secrets-<login>`, `children/<login>`, the bundles and the recovery copies.
- **The id is recorded beneath the name:** as the entry's `agent_id`, as the address of the key's user id, and in `.agent-id`. A parent is named by its id.
- **Rename:** `store-enroll.sh --rename` moves the names and keeps the id.
- **Repository description:** it gives both the Linux login and the agent id; the owner asked for that too.

**How to apply:** ask where an identifier will be SEEN before making it the name of anything.

Final, owner 2026-09-29 (third version): "in things like folder and file name, repo name, it's better to use the uuid not the name. Keep the names in the command along the uuid, the command underlying work with uuid, you get at the start the uuid from the name."

- **Stored by id:** `agent-fabric-secrets-<id>`, `<id>.asc`, the lineage key, `children/<id>`, the bundles, the recovery copies, and the owner's recovery key as `recovery-key-<fpr16>.asc`.
- **Commands take a login or an id** and resolve it first.
- **Repository description:** "Linux login: X. Agent id: Y."
- **A rename** changes the lineage `login` field and the description.

This landed in #64 as 9d671b6. The login-named version was superseded; ignore the section above about it.

*References: agent-owned-secrets-plan*

*Observed 2026-09-29 (fabric-coordinator)*

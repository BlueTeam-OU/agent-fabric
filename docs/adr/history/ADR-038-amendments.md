# ADR-038 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-29 — The recovery copy and the backup go to Proton Drive

The owner chose not to print the per-agent sheets: "you will simply
access proton drive via cli and save that there". Each key's recovery
copy, and a bundle of every store, therefore go to a Proton Drive
account dedicated to the fleet. Proton Drive has no app keys, so the
owner's own account never signs in on the agents' host. The trade was
named before it was taken: that account becomes the single recovery
point for every agent, so its 2FA and recovery phrase are what the owner
keeps. It was read back live on the coordinator: a backup, a
`--verify` of that backup against its manifest, and its recovery copy.

### Amendment 2026-09-29 — Recovery copies are encrypted to the owner's recovery key

A Proton session gives full access to the whole account, and an agent's
key can only be exported by that agent. So the plain copy the previous
amendment put in Proton would have made every agent able to read every
other agent's key, once each held a session. The owner chose option B
over the alternatives: every agent holding the fleet's session, or the
owner uploading each copy by hand. Under B, one recovery key protected
by the owner's passphrase receives every copy. Agents encrypt to its
public half and never hold a Proton session, the parent carries the
ciphertext, and only the owner, with the passphrase, can open a copy.
The coordinator's earlier plain copy is replaced, then deleted.

### Amendment 2026-09-29 — Keys and stores are named by the agent id

The owner decided that each agent has an id: a UUIDv7 minted from its
birth (ADR-039). The committed key, the lineage entry and the secrets
repository are now named by that id rather than by the login, so a
renamed login keeps them, and a reused name cannot inherit them. The
coordinator's repository `secrets-user` was renamed on GitHub to
`agent-fabric-secrets-019bbe31-2fff-7a2f-9849-96bdf286e011`, and its key
gained a user id addressed to that id.

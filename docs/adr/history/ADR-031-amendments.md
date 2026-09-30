# ADR-031 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — A move without its sync

Rule 4 said every named login gets the signed `secrets-sync` action once
the Doppler write is done. `fabric-accounts assign --no-sync`
(`runtime/control/accounts.mjs`) sends none, and says that each changed
login applies the move at its next `fabric-secrets sync` (review of
agent-fabric #53). The rule now names it.

### Amendment 2026-09-29 — Templates and assignments on the coordinator's store

The owner decided to move secrets off Doppler into a store per agent
(ADR-038). The templates are the coordinator's secrets, so they move
with it, into its store. An assignment can no longer be a reference
the account resolves: the coordinator puts the token itself into the
login's store. The coordinator cannot read that entry back, so it keeps
its own record of which account and which fingerprint it wrote. The
signed `secrets-sync` with `--expect` is unchanged, and stays the proof.

### Amendment 2026-09-30 — Doppler is retired: the store holds what Doppler held

Doppler is removed from the fabric (ADR-038, agent-fabric #69): every
account reads its own store, and the coordinator's templates and
signing key live in the coordinator's store. The template is only the store entry
and an assignment only the token put into the login's store; the
Doppler reference and its dual write are gone from §2, §4 and rules 1,
2 and 4.

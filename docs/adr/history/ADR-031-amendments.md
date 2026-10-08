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

### Amendment 2026-10-07 — The starting account is chosen at onboarding

§5 rule 8 added. The owner: "assigning the starting account should be
part of the onboarding of the agent". Three agents made the same day
were assigned with fabric-accounts afterwards; the token was written,
and every sync refused it until their keys reached main, so none could
start on plain Claude. new-agent's own first sync runs before that and
applied the rest of their store, so the account goes in before it.

### Amendment 2026-10-08 — A setup-token account's windows read from an inference reply

Every account had moved onto a setup-token, and the observer's sign-ins had lapsed, so `fabric-ctl all usage` showed no figure at all; the owner asked for the weekly allowances. A one-token call with each template's token came back with the full `anthropic-ratelimit-unified-*` set: utilisation, reset and status for both windows, different per account (docs/live-checks/2026-10-08-usage-from-inference-headers.md). The control agent's usage op now reads those headers for a setup-token account; the observer's `/usage` sign-ins remain for the per-model meters and are no longer needed for the windows. The `fabric-usage` path through the host executor still reports `setup-token` and is a carried item.

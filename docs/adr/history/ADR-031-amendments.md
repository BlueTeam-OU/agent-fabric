# ADR-031 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — A move without its sync

Rule 4 said every named login gets the signed `secrets-sync` action once
the Doppler write is done. `fabric-accounts assign --no-sync`
(`runtime/control/accounts.mjs`) sends none, and says that each changed
login applies the move at its next `fabric-secrets sync` (review of
agent-fabric #53). The rule now names it.

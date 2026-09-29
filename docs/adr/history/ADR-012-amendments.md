# ADR-012 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — The Doppler layout is replaced by each login's own store (ADR-038); rules 1-4 and 8 restated, 5-7 stand

Every account reads its own store (ADR-038; the fleet's enrolment is
recorded in docs/live-checks/2026-09-29-fleet-secrets-enrolment.md), so
the Doppler project this record chose is removed: the reader in
`fabric-secrets`, `enroll.sh` and its worker, the migration action, the
Doppler templates of `fabric-accounts`. What `enroll.sh` did for a new
account is `fabric-secrets provision`, which fills a child's store with
the parent's `put`. One rule changed its form: fill-from's denylist of
names never copied became an allowlist of names shared, with the
coordinator's credentials refused even when named — a denylist missed
the provisioning key once. The rules on a secret's shape and locator, a
destination with its credential, and tests by shape stand unchanged.

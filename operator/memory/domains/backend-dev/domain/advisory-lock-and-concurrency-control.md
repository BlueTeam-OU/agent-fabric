---
role: "backend-dev"
class: domain
description: SET LOCAL lock_timeout has no retroactive effect on a pg_advisory_xact_lock call issued before it, and this backend never uses SERIALIZABLE
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 42bc0c9685ab878c
  - 6ff677b0a9931c29
  - 9ee7054cbc56595b
  - bb6160303e0dff55
  - ef9348ca91ff912a
---

## SET LOCAL lock_timeout has no retroactive effect on a pg_advisory_xact_lock call issued before it, and this backend never uses SERIALIZABLE

Postgres session/transaction parameters like `lock_timeout` bound only statements executed after they are set — issuing `SET LOCAL lock_timeout` after the `pg_advisory_xact_lock` call it is meant to guard leaves that acquisition free to wait indefinitely. Confirmed live against a real Postgres container: `SET lock_timeout='1s'` issued *before* `pg_advisory_xact_lock(hashtextextended(...))` correctly raises "canceling statement due to lock timeout" under contention; reversing the order silently removes the bound. Separately: an exhaustive grep found zero uses of `SERIALIZABLE` isolation anywhere in the backend source — all concurrency control in this backend is `SELECT ... FOR UPDATE` row locks (used across `IJourneyRepository`, `IAdRepository`, `ICampaignRepository`, `AdminDeviceRegistryRepository`, `DriverErasureRepository`, `OperatorRepository`, `DeviceCredentialRepository`, `DevicePrincipalRepository`, and others) plus `hashtextextended`-keyed advisory locks for run-level/table-free serialization. New concurrency-sensitive repository code should follow that same pattern — advisory lock with an explicit prior lock_timeout, or FOR UPDATE — rather than reaching for SERIALIZABLE.

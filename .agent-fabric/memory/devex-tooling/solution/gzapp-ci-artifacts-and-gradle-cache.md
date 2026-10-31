---
role: "devex-tooling"
class: solution
topic: "gzapp-ci-artifacts-and-gradle-cache"
description: "gzapp Actions storage audit: unexpired artifacts are retention, not a leak; Gradle caches look unread but are weekly by design; a cancelled shard still runs a cancelled()-guarded step"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5128822be394b82c
---

## gzapp Actions storage audit: unexpired artifacts are retention, not a leak; Gradle caches look unread but are weekly by design; a cancelled shard still runs a cancelled()-guarded step

Audited 2026-10-18 (j144, gzapp #1126).

- **Artifacts.** "expired: false" on every artifact is just `retention-days: 14`. Read `expires_at` before calling anything a leak. What made it large was the upload condition: `always()` uploaded four dotnet-test-results artifacts on every run, 798 in all, 328 MB. #1126 changes it to `failure() || cancelled()`.
- **Gradle caches.** The two ~1.7 GB entries (driver and passenger) show last_accessed == created_at. They only look unused: only `cache-warm.yml` (weekly cron `17 4 * * 1`) and `release-gate.yml` build the APK and restore them, by the owner's decision D7. They are not a defect.
- **Cancelled shards.** Cancelled run 38371677110 shows the upload step running in all four cancelled test shards. A job timeout is reported as a cancellation, so a `cancelled()`-guarded upload still runs. No reviewer could run the timeout case directly.
- **Billing.** The org billing endpoint `orgs/<org>/settings/billing/actions` returns 410 (moved). `repos/<r>/actions/cache/usage` still works.

*Observed 2026-10-18 (devex-tooling)*

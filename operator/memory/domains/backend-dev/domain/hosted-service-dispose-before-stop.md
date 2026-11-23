---
role: "backend-dev"
class: domain
topic: "hosted-service-dispose-before-stop"
description: A hosted service with a retry loop must survive Dispose before or during StopAsync, and a store error during the stop
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - e926f8af8d283218
---

## A hosted service with a retry loop must survive Dispose before or during StopAsync, and a store error during the stop

WebApplicationFactory hosts (notably ones derived with WithWebHostBuilder) can dispose a hosted service's container before, or concurrently with, StopAsync. A service that disposes a CancellationTokenSource in Dispose and cancels it in StopAsync then throws ObjectDisposedException at test teardown — only while its background loop is running, so it surfaces as 1–3 random host-test failures in a full suite, never in the service's own unit tests.

Shape that holds (gzapp I18nBaselinePublication, #1238 5e57f75d4 + 0e0f272b0): decide-to-cancel and dispose under one lock with a disposed flag (a flag alone races); Dispose cancels then disposes; StopAsync returns when disposed. And in the loop: a write in flight when the stop cancels may fail with the store's OWN error, not OperationCanceledException — a `catch when (!stopping.IsCancellationRequested)` lets it escape and faults StopAsync; add a second catch that logs at Warning and returns. Pin it with a store that waits for the token then throws its own exception.

Related: [[caller-cancellation-is-not-unavailability]], [[xunit-v3-exit-window]].

*References: caller-cancellation-is-not-unavailability, xunit-v3-exit-window*

*Observed 2026-11-10 (backend-dev)*

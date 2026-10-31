---
role: "rust-services-dev"
class: domain
topic: "tracing-set-default-misses-events"
description: "a thread-scoped tracing subscriber in a unit test misses events when other tests hit the same callsite; log tests need their own binary"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - e4598cde4f07856b
---

## a thread-scoped tracing subscriber in a unit test misses events when other tests hit the same callsite; log tests need their own binary

`tracing::subscriber::set_default` in a `#[tokio::test]` unit test was
flaky (about one full-suite run in four): another test in the same
process reached the same `tracing::info!` callsite with no subscriber,
the callsite's interest was cached as "never", and the scoped
subscriber's events were never built. Alone, the test passed every time.

Rule: a test that asserts on log lines is its own integration-test
binary with the process-wide subscriber (`tracing_subscriber::fmt()
… .init()`), one test per binary. That is the pattern of
`tests/anthropic-passthrough/tests/{time_bounds_log,activation_log,
safe_metadata,labels,credential_log}.rs`.

Found on PR #27 (2026-10-10), ADR-012 rule 17's test, moved before the
PR opened.

*Observed 2026-10-10 (rust-services-dev)*

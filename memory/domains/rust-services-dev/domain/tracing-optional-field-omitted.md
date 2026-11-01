---
role: "rust-services-dev"
class: domain
topic: "tracing-optional-field-omitted"
description: "How to make a tracing log field appear only when a value is recorded (absent, not \"None\"), and validating an HTTP header's shape before logging it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d6509022a18f73dc
---

## How to make a tracing log field appear only when a value is recorded (absent, not "None"), and validating an HTTP header's shape before logging it

In `tracing` 0.1, `Option<T: Value>` is itself a `Value`, and `None` records nothing. So
`field = opt.map(tracing::field::debug)` leaves the field off the line entirely when there
is no value, and the fmt layer prints `field="…"`, Debug-escaped, when there is one.
`field = ?opt` prints `field=None` on every line instead. Use the first form for metadata
that is only conditionally recorded (for example a 429's retry-after: agent-fabric-gateway
PR #70, `record_attempt` in `crates/runtime/gateway-runtime/src/handler.rs`).

When a recorded header value must have a closed shape and be "never cut", validate it
whole and record nothing otherwise:
- one `get_all` instance only;
- a length bound before parsing;
- `to_str()` to reject obs-text bytes;
- delay-seconds as all ASCII digits;
- `httpdate::parse_http_date` for the three RFC 9110 date forms.

hyper's server feature already brings in `httpdate`, so a direct dependency on it adds no
crate.

Prove the test is live with a revert test: stub the recorder to `None` and check that the
wire tests fail.

*Observed 2026-10-18 (rust-services-dev)*

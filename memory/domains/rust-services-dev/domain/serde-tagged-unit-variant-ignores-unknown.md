---
role: "rust-services-dev"
class: domain
topic: "serde-tagged-unit-variant-ignores-unknown"
description: serde internally tagged enum unit variant accepts unknown keys despite deny_unknown_fields; use an empty struct variant
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - b4a9194b389e950f
---

## serde internally tagged enum unit variant accepts unknown keys despite deny_unknown_fields; use an empty struct variant

With `#[serde(tag = "op", deny_unknown_fields)]`, a **unit** variant
(`Status`) still deserializes `{"op":"status","extra":1}` — the attribute
does not reach unit variants of an internally tagged enum. An empty
**struct** variant (`Status {}`) refuses the extra key. Duplicate keys,
the duplicate tag included, are refused by derive in either form.

Derived deserializers also accept a JSON array for a struct (see
[[serde-derive-accepts-arrays]]): check the first non-space byte is `{`
before `from_slice` when a request must be an object.

Found by a unit test on the gateway's control channel request type,
`apps/agent-fabric-gateway/src/control.rs` (PR #25, 2026-10-10).

*References: serde-derive-accepts-arrays*

*Observed 2026-10-10 (rust-services-dev)*

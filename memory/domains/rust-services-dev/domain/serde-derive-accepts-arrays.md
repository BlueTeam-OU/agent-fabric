---
role: "rust-services-dev"
class: domain
topic: "serde-derive-accepts-arrays"
description: "A derived serde struct also deserializes from a JSON array; a field probe that must only accept objects needs a map-only visitor"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 1a00947024bf3403
---

## A derived serde struct also deserializes from a JSON array; a field probe that must only accept objects needs a map-only visitor

`#[derive(Deserialize)] struct Probe { model: … }` accepts `["x"]` as well as `{"model":"x"}`.
serde's derive implements `visit_seq` in field order. A selector or routing probe that must refuse
a non-object body therefore needs a hand-written `Visitor` with only `visit_map`, called through
`deserialize_map`. Found by a unit test in agent-fabric-gateway
`crates/protocol/anthropic/src/selector.rs` (PR #5, commit "protocol-anthropic: …").

*Observed 2026-10-07 (rust-services-dev)*

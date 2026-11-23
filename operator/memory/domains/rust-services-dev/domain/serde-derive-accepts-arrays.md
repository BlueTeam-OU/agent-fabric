---
role: "rust-services-dev"
class: domain
topic: "serde-derive-accepts-arrays"
description: "A derived serde struct also deserializes from a JSON array; a field probe that must only accept objects needs a map-only visitor"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 06a351e2fc4b0e67
  - 1a00947024bf3403
---

## A derived serde struct also deserializes from a JSON array; a field probe that must only accept objects needs a map-only visitor

`#[derive(Deserialize)] struct Probe { model: … }` accepts `["x"]` as well as `{"model":"x"}`:
serde's derive implements `visit_seq` in field order. A selector or routing probe that must refuse
a non-object body therefore needs a hand-written `Visitor` with only `visit_map`, called through
`deserialize_map`. Carried in agent-fabric-gateway `crates/protocol/core/src/selector.rs`
(`Probe`/`ProbeVisitor`, with the test that `["model"]` is `SelectorError::Malformed`); the
selector moved there from `crates/protocol/anthropic/src/selector.rs` in commit 6a07a50
("protocol/core: the route selector and the error codes, shared by every family"). First found by
a unit test in PR #5. Checked at gateway origin/main 86a1316: `cargo test -p gateway-protocol-core
selector`, 8 passed.

*Observed 2026-10-20 (rust-services-dev)*

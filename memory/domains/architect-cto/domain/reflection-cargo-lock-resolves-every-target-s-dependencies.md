---
role: "architect-cto"
class: domain
topic: "reflection-cargo-lock-resolves-every-target-s-dependencies"
description: "Cargo.lock resolves dependencies for every target, including wasm-only edges hidden under a cfg, so an exact pin in one wasm-only dependency can make a native-only crate unresolvable; vendoring the pinning crate with its pins relaxed…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 077ef791eae8f6b0
---

## Cargo.lock resolves dependencies for every target, including wasm-only edges hidden under a cfg, so an exact pin in one wasm-only dependency can make a native-only crate unresolvable; vendoring the pinning crate with its pins relaxed costs far less than forking the side that pins

InterWeave 2026-10-03: "depends unconditionally (under a cfg the
lockfile cannot see) on i-slint-renderer-skia -> glow 0.18 -> js-sys
~0.3.100, while libp2p-swarm 0.48.0 pins wasm-bindgen-futures =0.4.58"
(01a10039-d532); DECISION 01a10052-7ddd: "vendor wasm-bindgen-futures
with its pins relaxed… a 3-line diff — against 13,258 lines". ADR-0054
records the vendoring, not the Cargo behaviour.

*Observed 2026-10-23 (architect-cto)*

---
role: "rust-ui-dev"
class: domain
topic: "type-encode-ui-rules"
description: "Agreeing an API a client renders or acts on -- put the UI's rule in the type: closed error enums, markers for forbidden values, diagnostics off the view's type, tested code tables across FFI"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ee698f86f8cd4b82
---

## Agreeing an API a client renders or acts on -- put the UI's rule in the type: closed error enums, markers for forbidden values, diagnostics off the view's type, tested code tables across FFI

When negotiating a seam the client consumes, ask for the rule in the type, so a wrong
caller fails at compile time rather than at a person:
- Errors the person sees: a CLOSED enum (no #[non_exhaustive]), one variant per cause a
  person can act on; the view maps each through a stable text key, and any detail string is
  for the log only. A new variant then breaks the client's exhaustive match.
- A value a ruling forbids writing: make it unrepresentable (a setter taking
  Option<StayReachable>, a unit marker, so "off" removes the entry and the default is never
  written), instead of documenting "do not pass X".
- Raw diagnostic codes live on a separate diagnostics accessor, not on the item type the
  view draws, so a view cannot render one by accident.
- Across an FFI boundary (Rust <-> Kotlin over JNI) the compiler stops checking: a pair of
  integer code tables needs a test tying them, or a swapped code turns "runtime died" into a
  restart loop.

*Observed 2026-10-15 (rust-ui-dev)*

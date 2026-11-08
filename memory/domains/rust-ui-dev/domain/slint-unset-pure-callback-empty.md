---
role: "rust-ui-dev"
class: domain
topic: "slint-unset-pure-callback-empty"
description: "A Slint global pure callback with no Rust handler answers \"\" — every window instance must wire it, or what it computes goes blank"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 90d0a18a5203adec
---

## A Slint global pure callback with no Rust handler answers "" — every window instance must wire it, or what it computes goes blank

A `pure callback f(string) -> string` on a Slint global that Rust never sets returns the default, an empty string, with no error. Each exported window (component) has its own global instance, so wiring one window does not wire another. Seen 2026-11-07 (InterWeave j95, 6a5394c86): wrapping every accessible-label in `Drawn.spoken(...)` blanked all of RefusalWindow's labels until `wire_drawn` was called for it too; tests/refusal.rs caught it by failing to find labels. Rule: one wiring function, called at every `Window::new()`, and a test per window that looks something up by label.

*Observed 2026-11-07 (rust-ui-dev)*

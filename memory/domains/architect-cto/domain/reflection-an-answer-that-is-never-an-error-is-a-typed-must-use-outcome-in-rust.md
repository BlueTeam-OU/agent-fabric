---
role: "architect-cto"
class: domain
topic: "reflection-an-answer-that-is-never-an-error-is-a-typed-must-use-outcome-in-rust"
description: "If a wire answer is never an error, the Rust port does not carry it as Err but returns a typed outcome marked must_use, since a caller ending in call()?; discards the Ok value and would show a refused write as made, and with -D warnings…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - c97fa1670292881a
---

## If a wire answer is never an error, the Rust port does not carry it as Err but returns a typed outcome marked must_use, since a caller ending in call()?; discards the Ok value and would show a refused write as made, and with -D warnings the build fails until each caller handles it

InterWeave 2026-10-23: "Both discard the Ok value with '?;', so they
would compile and show a superseded set as made" (01a166dd); "the
build failing until each caller handles it is the point" (01a166fe).
ci.yml runs clippy with -D warnings; TrustChange is on the j65 branch
at writing.

*Observed 2026-10-23 (architect-cto)*

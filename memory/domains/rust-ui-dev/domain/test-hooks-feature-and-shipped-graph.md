---
role: "rust-ui-dev"
class: domain
topic: "test-hooks-feature-and-shipped-graph"
description: "Test-only hooks in Rust behind a cargo feature that no shipped build can resolve, and how to read the shipped feature graph (cargo tree -e normal -f '{p}|{f}', not -e features)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f522039e8cd26695
---

## Test-only hooks in Rust behind a cargo feature that no shipped build can resolve, and how to read the shipped feature graph (cargo tree -e normal -f '{p}|{f}', not -e features)

When a UI acceptance check needs a hook (force a read failure, set a tiny ceiling, show a page
that is otherwise unreachable), put it behind a feature that the shipped binary cannot carry:
- declare `test-hooks = []` in the crate that holds the hooks; never in `default`;
- enable it only through a dev-dependency on the crate itself or from a test crate, never from a
  shipped binary's `[dependencies]` (cargo unifies features: one normal edge turns it on for all);
- gate the hook code with `cfg(feature = "test-hooks")`, so a shipped build contains none of it.
Prefer the model layer when a case is cheaper and complete there; the rendered proof is the gate's.

To show a shipped build does not carry it, read the RESOLVED features per package:
`cargo tree -p <bin> -e normal -f '{p}|{f}'` (and the Android library with the release's exact
cargo-ndk target/flags). `cargo tree -e features` shows a feature only where a dependent turns
it on, so a root package's own feature never appears there — a check built on it can pass a
binary that ships the hook. Say in the PR which cases are proven headless and which over the
platform's accessibility stack. In InterWeave this is now CI
(tools/checks/check_shipped_test_hooks.sh, #514); elsewhere, add the same guard with a mutation
self-test.

*Observed 2026-10-31 (rust-ui-dev)*

---
role: "rust-ui-dev"
class: domain
topic: "global-sink-test-isolation"
description: "A Rust test that counts lines in a process-global log or sink flakes when sibling tests in the same binary emit the same line in parallel -- give it its own binary"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a6eb3398bb2df965
---

## A Rust test that counts lines in a process-global log or sink flakes when sibling tests in the same binary emit the same line in parallel -- give it its own binary

cargo test runs a test binary's tests on parallel threads sharing one process. A test that
asserts "warning X was (not) logged" against a process-wide capture sees sibling tests'
copies of X: it failed 8 of 8 on a 10-core host, passed alone and with --test-threads=1,
and was green in CI by timing. The same class had been fixed once before in another
overlay test and recurred in the next one. When a test reads global state (a log capture, an
audit sink, an env var), put it in its own tests/<name>.rs binary, or make the emitted line
carry an identifier the test filters on. Reproduce such a suspicion with the whole binary
in parallel on a many-core host, with the single-threaded run as the control.

*Observed 2026-10-15 (rust-ui-dev)*

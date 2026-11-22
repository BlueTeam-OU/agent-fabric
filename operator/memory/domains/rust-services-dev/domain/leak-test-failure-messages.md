---
role: "rust-services-dev"
class: domain
topic: "leak-test-failure-messages"
description: "A secret-leak test reports a hit by name and offset, never the bytes; a drop's log line names its class, never the error's Display"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f40d2cebd2e11f86
---

## A secret-leak test reports a hit by name and offset, never the bytes; a drop's log line names its class, never the error's Display

Two leak paths a credential-containment test must close on purpose:

1. **The negative test's own failure message is a log line.** A test that scans captured output for a
   secret must report a hit by the secret's *name* and the offsets, and compare rather than print in
   every assertion (the controls included). Printing the secret or the captured stream in `assert!`
   text writes it into the CI log on the first failure. CodeQL's rust/cleartext-logging flags it
   (high), and the architecture role ruled it the leak class itself, not a test nit
   (InterWeave #336, apps/claude-channel/tests/threat_rows.rs, fixed ff067ece, 5c9b2212).
2. **Log the failure's class, never the error.** A dropped or failed message gets a fixed line
   per failure class. Formatting an error type's `Display`/`Debug` carries whatever the variant
   holds: in InterWeave, channel-core's DuplicateToken names a live reply token, which is a bearer.
   Prove it with a unit test whose control asserts the error's `to_string()` *does* contain the
   secret and the emitted line does not (serve.rs, #336, commit 80cf7080).

**How to apply:** while writing any leak test, read its failure messages as if they were output.
For every `eprintln!`/`tracing` of an error value on a peer-data path, ask what its variants carry.
An error type in another role's crate goes to that role as an OBSERVATION.

*Observed 2026-10-22 (rust-services-dev)*

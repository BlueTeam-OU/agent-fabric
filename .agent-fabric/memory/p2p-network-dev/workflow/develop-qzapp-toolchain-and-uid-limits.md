---
role: "p2p-network-dev"
class: workflow
topic: "develop-qzapp-toolchain-and-uid-limits"
description: "what this login cannot reproduce locally on develop-qzapp — the pinned Rust toolchain, and a second uid for cross-account socket tests"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b035e16bd8aa92c9
---

## what this login cannot reproduce locally on develop-qzapp — the pinned Rust toolchain, and a second uid for cross-account socket tests

On develop-qzapp this login has only Fedora's Rust 1.99 at /usr/bin and no rustup. InterWeave pins 1.98.1, and clippy 1.99 fails main's code (double_must_use). So lint my own package with `cargo clippy -p <pkg> --all-targets --no-deps -- -D warnings`, and rely on CI for the rest. Reported to devex-tooling 2026-10-19 (OBSERVATION 01a1538b). A test that needs a second kernel uid (e.g. SO_REUSEPORT across accounts) cannot be run from this session. A rootless user-namespace probe with subuid mapping was refused by the session's safety check, so do not retry it. Report such a property as unverified and ask the owner, or ask devex-tooling for CI with a second account.

*Observed 2026-10-19 (p2p-network-dev)*

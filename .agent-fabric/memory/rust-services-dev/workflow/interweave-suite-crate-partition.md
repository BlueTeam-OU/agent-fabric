---
role: "rust-services-dev"
class: workflow
topic: "interweave-suite-crate-partition"
description: "InterWeave root test suites (tests/<suite>/) are partitioned by file between open PRs, not by crate; library and app crates stay one open PR per crate"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 230dcf9c50befca4
---

## InterWeave root test suites (tests/<suite>/) are partitioned by file between open PRs, not by crate; library and app crates stay one open PR per crate

In InterWeave, two open PRs may both change a root test suite crate under tests/<suite>/, such as tests/desktop-e2e, as long as they share no file and neither touches the suite's harness (tests/<suite>/tests/common, tests/support) or its Cargo.toml.

**Why:** architect-cto's DECISION 01a1631f (2026-10-22). Each tests/*.rs is its own test binary, so hunks in different files cannot meet. CLAUDE.md §9 partitions by file set. The remit's "two open pull requests never change the same crate" guards the same thing.

**How to apply:**
- Before opening a PR in tests/<suite>/, check that no open PR or pushed branch touches the same test file, the harness or the manifest (`fabric-pr gate --in-flight --path`).
- For a library or application crate, one open PR per crate is still the rule.
- architect-cto asked fabric-coordinator to write this exception into the remit.

*Observed 2026-10-22 (rust-services-dev)*

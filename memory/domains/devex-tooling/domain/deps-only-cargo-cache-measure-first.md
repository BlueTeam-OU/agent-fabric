---
role: "devex-tooling"
class: domain
topic: "deps-only-cargo-cache-measure-first"
description: "before proposing a cargo cache in CI, measure how much of the build is dependencies — cargo clean -p every workspace package and rebuild"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - b1f29ca1a95a1f61
---

## before proposing a cargo cache in CI, measure how much of the build is dependencies — cargo clean -p every workspace package and rebuild

A cargo cache that holds only dependency builds saves only the dependency share of a build. In a workspace whose cost is its own test binaries, that share is small. On agent-fabric-gateway (2026-10-18), 72 of 84 crates were dependencies, but they were only ~19% of the test build's time.

**Why:** the CI log's crate count suggested most of the build would be saved. The measurement showed otherwise, and the proposal would otherwise have promised a saving it could not deliver.

**How to apply:** with a scratch `CARGO_TARGET_DIR` and `CARGO_INCREMENTAL=0`, time a cold `cargo test --workspace --all-targets --no-run --locked`. Then run `cargo clean --package=<each workspace package>` and time it again; the difference is the cache's ceiling. `du` the cleaned target for the cache's size. Remove the scratch target afterwards. Don't run the test with `CARGO_TARGET_DIR=` set empty: cargo refuses an empty value.

*Observed 2026-10-18 (devex-tooling)*

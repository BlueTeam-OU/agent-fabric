---
role: "devex-tooling"
class: domain
topic: "cargo-features-read-per-package-resolved"
description: "a cargo workspace's CI builds each crate only with the features the workspace unifies, so a defect that shows only without them passes; and `cargo tree -e features` edges omit a root package's own features; read features per package…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dcebbf231a5b22ca
---

## a cargo workspace's CI builds each crate only with the features the workspace unifies, so a defect that shows only without them passes; and `cargo tree -e features` edges omit a root package's own features; read features per package, resolved

`cargo clippy --workspace --all-targets` builds a member with the union of features every
member turns on. InterWeave's apps/human-desktop enables ui-slint's `desktop` without a
condition, so ui-slint was never linted without it. rust-ui-dev-01 saw a dead-code defect pass
CI twice, and a `cfg_attr(..., expect(dead_code))` that only a featureless lint can enforce.
`cargo clippy -p <pkg>` failed while the workspace lint passed. Three more members had the same
gap (chat-protocol, human-store, test-support). InterWeave #461 (tools/ci/own_features.sh)
now lints, one `cargo clippy -p` per package, every package whose own feature set
(`cargo tree -p`, dev-deps included) differs from the workspace build's. architect-cto pointed
out a gap the script still has: a member whose build fails on a dependency feature that another
member turns on.

Same trap when checking what ships (InterWeave #514, check_shipped_test_hooks.sh). An edge in
`cargo tree -e features` shows a feature only where a dependent turns it on. A root package's
own feature never appears there. The guard reads resolved features instead:
`cargo tree -e normal -f '{p}|{f}'`, per shipped build.

**How to apply:** in any Rust repo's CI, or in a guard that claims something about features,
lint or read each package with its own feature set. Never infer from the workspace build or
from feature edges. Compute the package list on each run, so a new member is covered.

*Observed 2026-10-31 (devex-tooling)*

---
role: "rust-services-dev"
class: domain
topic: "two-version-probe-renamed-path-copies"
description: "to probe two semver-compatible versions of one crate side by side, copy each registry src into a renamed path crate; cargo refuses two =x.y.z deps of one name"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 71df44151cd3bf60
---

## to probe two semver-compatible versions of one crate side by side, copy each registry src into a renamed path crate; cargo refuses two =x.y.z deps of one name

Cargo cannot resolve `old = { package = "unicode-ident", version = "=1.0.26" }` beside `new = { ... "=1.0.27" }`
in one probe crate. Two semver-compatible versions of one package conflict ("failed to select a version").
What works offline is this: copy `~/.cargo/registry/src/<index>/<crate>-<v>/src` into `old/` and `new/`, give
each a minimal Cargo.toml with a distinct package name and `[lib] name`, and depend on them by path. Used on
2026-11-04 (gateway j58, PR #80) to show that is_xid_start and is_xid_continue agree on every scalar value across
unicode-ident 1.0.26 -> 1.0.27.

**Why:** a behaviour claim in a lockfile commit message needs a probe ([[dependency-diff-check-feature-gate]]),
and the obvious two-dependency probe fails for any patch bump.
**How to apply:** this works only for a crate without a build script or its own dependencies, or one whose
dependencies are also written into the minimal manifest. Run it with `cargo +<pinned channel> run --offline`.

*References: dependency-diff-check-feature-gate*

*Observed 2026-11-04 (rust-services-dev)*

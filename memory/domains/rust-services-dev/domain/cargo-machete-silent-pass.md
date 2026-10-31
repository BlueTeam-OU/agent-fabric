---
role: "rust-services-dev"
class: domain
topic: "cargo-machete-silent-pass"
description: "cargo-machete 0.9.2 default mode skips dev-deps; --with-metadata reports unreadable crates clean with exit 0"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 1ff8a3fcfd89be4c
---

## cargo-machete 0.9.2 default mode skips dev-deps; --with-metadata reports unreadable crates clean with exit 0

Measured with cargo-machete 0.9.2 on the gateway workspace, 2026-10-10:

- **Default mode reads only `[dependencies]`.** An unused `hyper` dev-dependency passed in default mode and was caught by `--with-metadata`.
- **`--with-metadata` passes crates it could not read.** When cargo metadata fails (for example a broken path dependency), it prints "error when handling <manifest>" on stderr for each crate, counts each one clean, and exits 0. Nine members gave nine lines and exit 0.
- **Its own metadata call is not `--locked`,** so it rewrites Cargo.lock.
- **Exit codes:** 1 means unused dependencies were found, 2 is the tool's own error, and 101 is a panic.

The guard that handles all of this is `cargo xtask machete` (agent-fabric-gateway xtask/src/main.rs, #36/#37):
1. It runs `cargo metadata --locked` first.
2. It then runs `--with-metadata`.
3. It fails on the stderr "error when handling" line.
4. It names an unused dependency only when the exit code is 1.

CI pins both tools as tarballs with SHA-256 digests in ci.yml's env, matching agent-fabric's projects/registry.json entry. The registry spells the machete version without its tag's `v`.

*Observed 2026-10-10 (rust-services-dev)*

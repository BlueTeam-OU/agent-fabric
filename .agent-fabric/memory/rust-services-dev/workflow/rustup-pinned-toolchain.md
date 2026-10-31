---
role: "rust-services-dev"
class: workflow
topic: "rustup-pinned-toolchain"
description: "which cargo/rustc this account builds the gateway with, and since when the rust-toolchain.toml pin is honoured"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e7ea5c3e85fa3e42
---

## which cargo/rustc this account builds the gateway with, and since when the rust-toolchain.toml pin is honoured

Until 2026-10-19 this account had no rustup, so cargo was Fedora's /usr/bin 1.99.0 and the gateway's rust-toolchain.toml pin (1.97.1) was ignored; local gateway results before then (incl. gateway#70) ran on 1.99, not the pin CI uses. On 2026-10-19 `fabric-tools --install rustup` and `--install cargo-deny`, run from the gateway working copy (the gateway's registry tools list both), put rustup 1.29.1 and cargo-deny 0.20.2 in ~/.local/bin; cargo there now resolves to 1.97.1 with clippy. Check with `fabric-tools` from the working copy. Prompted by devex-tooling's INFO 01a154bc (InterWeave pin, check_rustc_pin.sh fixed in InterWeave#311).

*Observed 2026-10-19 (rust-services-dev)*

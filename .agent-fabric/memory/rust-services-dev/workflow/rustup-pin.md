---
role: "rust-services-dev"
class: workflow
topic: "rustup-pin"
description: "Which cargo runs on this account, and why a rust-toolchain.toml pin was ignored before 2026-10-19"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 440fc85fa7717609
---

## Which cargo runs on this account, and why a rust-toolchain.toml pin was ignored before 2026-10-19

develop-qzapp's system Rust is Fedora's (1.99.0 on 2026-10-19). A
project's rust-toolchain.toml pin is honoured only by rustup; before
2026-10-19 no Rust account had it, so agent-fabric-gateway (pin 1.97.1)
built and linted with 1.99 here. Installed `fabric-tools --install rustup`
(1.29.1) and `--install cargo-deny` (0.20.2) from the gateway working copy;
~/.local/bin/cargo now precedes /usr/bin, and the gateway gives
cargo/rustc/clippy 1.97.1. ~/.rustup holds the toolchains (624M after
1.97.1); count it in disk hygiene [[disk-hygiene]]. A check that calls
clippy-driver or rustc by PATH outside cargo may still reach Fedora's
(InterWeave's check_rustc_pin.sh, fixed by InterWeave#311, per
devex-tooling's INFO 01a154bc).

*References: disk-hygiene*

*Anchors: `projects/registry.json::rustup`*

*Observed 2026-10-19 (rust-services-dev)*

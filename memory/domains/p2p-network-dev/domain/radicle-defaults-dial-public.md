---
role: "p2p-network-dev"
class: domain
topic: "radicle-defaults-dial-public"
description: "A radicle-node on rad auth's default config joins the public network; what local-only takes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: "radicle-spike"
    working_copy: "radicle-spike"
derived_from:
  - 0964c2cdf6f24b9e
---

## A radicle-node on rad auth's default config joins the public network; what local-only takes

Radicle 1.10.3 (heartwood 7e1cb406bb93): `rad auth` writes `network: main`, `peers: dynamic`, `connect: []`. With `connect` and the address book empty, the node adds its network's bootstrap seeds (iris/rosa.radicle.network for `main`; none for `test`) — `crates/radicle-node/src/runtime.rs:175` — and `maintain_connections` (`crates/radicle-protocol/src/service.rs:2560`) dials known addresses only when peers are `dynamic`. Other dial paths: the `connect` list at init and an operator's `Command::Connect`. `network` affects nothing but the bootstrap list.

Local-only = `network: test` + `peers: static` + `connect: []` + loopback `listen`, enforced by running the node in an unprivileged `unshare -rn` namespace (loopback only; works without root on Fedora 43). Consequence: a second node must join that namespace (`nsenter -U -n`) to reach it.

Shown in radicle-spike findings/01-seed-on-host.md. Related: [[radicle-stale-control-socket]].

*References: radicle-stale-control-socket*

*Observed 2026-10-07 (p2p-network-dev)*

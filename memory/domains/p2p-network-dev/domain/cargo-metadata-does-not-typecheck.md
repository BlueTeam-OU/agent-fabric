---
role: "p2p-network-dev"
class: domain
topic: "cargo-metadata-does-not-typecheck"
description: "a guard built on `cargo metadata --locked` cannot see a pin whose source does not compile against it — only `cargo check --locked` can"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 21222534c27dc68e
---

## a guard built on `cargo metadata --locked` cannot see a pin whose source does not compile against it — only `cargo check --locked` can

`cargo metadata --locked` resolves a dependency graph without
type-checking a line of it. So a harness pinning a revision of a
first-party crate by `rev =` can import symbols that revision does not
define, and a guard asking `cargo metadata` reports OK forever.

Measured in InterWeave: SPIKE-004's harness pinned `cf04e7b7`, whose
`interweave-transport-libp2p` exports no `Attributing`,
`DialAttribution` or `always`, while `harness/src/production.rs`
imports all three. `check_spike_locks.sh` passed across two stages; a
blind review found it (PR #109).

The fix is `cargo check --locked` per harness, added as a second phase
in `tools/checks/check_spike_locks.sh` (081684f). Classify its failures
the way the lock phase does: `error[E` or `could not compile` is a
finding, anything else is cargo never reaching rustc — a git remote it
cannot fetch a pinned rev from, a registry index, a toolchain — and
stays exit 2.

Cost on this host at `cargo -j 2`: 54.5 s cold per harness, 1.6 s warm
for three.

Related: [[frozen-spike-pin-follows-last-recorded-run]].

*References: frozen-spike-pin-follows-last-recorded-run*

*Observed 2026-09-20 (p2p-network-dev)*

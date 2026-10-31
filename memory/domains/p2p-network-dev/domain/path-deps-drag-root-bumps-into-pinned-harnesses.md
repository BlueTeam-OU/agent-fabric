---
role: "p2p-network-dev"
class: domain
topic: "path-deps-drag-root-bumps-into-pinned-harnesses"
description: "A harness that pins libp2p exactly but path-depends on workspace crates is not pinned — cargo resolves both majors side by side (0.56 + 0.57, three yamux) after a root bump; pin first-party crates by git rev"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f971df75cb6fbea
---

## A harness that pins libp2p exactly but path-depends on workspace crates is not pinned — cargo resolves both majors side by side (0.56 + 0.57, three yamux) after a root bump; pin first-party crates by git rev

Measured on the libp2p 0.56 → 0.57 bump (InterWeave, 2026-09-19): two
frozen spike harnesses pinned `libp2p = "=0.56.0"` for themselves while
path-depending on production crates that inherit libp2p from the root
manifest. After the root moved, cargo satisfied both: the refreshed lock
held libp2p 0.56.0 AND 0.57.0 and yamux 0.12.1, 0.13.10 and 0.14.0
(+2342 lines). The harness then builds a graph its recorded evidence
does not describe, and re-admits the vulnerable muxer the bump existed
to remove (yamux 0.12.1's remote panic has no RustSec advisory, so
cargo-deny is silent about it).

**Fix that was ruled:** do not cut the production crates out (a harness
building a copy of the gate measures a copy); replace each path
dependency with `{ git = "<this repository>", rev = "<sha>" }`. After
that every harness resolved ONE libp2p and the locks shrank. deny.toml's
`unknown-git = "deny"` needs the repository allowed for it.

**How to apply:** a pin is only as exact as the least-pinned edge into
the graph. On any root dependency bump, run the spike/harness lock
check and read `cargo tree -d` for duplicate majors; a harness that must
stay frozen pins its first-party crates by revision. Then type-check it
at that revision — see [[cargo-metadata-does-not-typecheck]] and
[[frozen-spike-pin-is-the-recording-commits-tree]].

*References: cargo-metadata-does-not-typecheck, frozen-spike-pin-is-the-recording-commits-tree*

*Observed 2026-10-15 (p2p-network-dev)*

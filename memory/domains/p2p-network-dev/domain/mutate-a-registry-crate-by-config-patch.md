---
role: "p2p-network-dev"
class: domain
topic: "mutate-a-registry-crate-by-config-patch"
description: "To prove a test pins a dependency's constant (libp2p-kad MAX_NUM_STREAMS), patch a copy from the command line, never the manifest; plus two libp2p-kad 0.49 seat/stream facts"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 9ab3c410c501ed30
---

## To prove a test pins a dependency's constant (libp2p-kad MAX_NUM_STREAMS), patch a copy from the command line, never the manifest; plus two libp2p-kad 0.49 seat/stream facts

A test that asserts a third-party bound (e.g. libp2p-kad's 32 inbound streams per connection) is proved load-bearing by running it against a mutated copy of that crate without touching any manifest:
`cp -r ~/.cargo/registry/src/<index>/libp2p-kad-0.49.0 <dir>`, edit the constant, then `cargo test --config 'patch.crates-io.libp2p-kad.path="<dir>"' …`, then `git checkout Cargo.lock` and delete the copy. Keep the copy under /home, not tmpfs. (InterWeave S6, 2026-10-12: ceiling 64 → the test saw 64 kept and failed.)

libp2p-kad 0.49 facts read for it:
- An inbound stream that never sends a request has no timeout (only outbound streams are bounded by `substreams_timeout`). Past 32, a new stream is dropped unless an older one is idle after a served request (`WaitingMessage { first: false }`), which is cancelled instead (`handler.rs` ~521).
- A full k-bucket keeps CONNECTED occupants: `insert` queues a newcomer as pending only when the bucket's head is disconnected, then replaces it after `pending_timeout`, 60 s by default (`kbucket/bucket.rs` ~334). With a 60 s idle connection timeout, an idle honest seat can therefore be taken by a connected newcomer.
- A raw stream opener needs no crate: a `ConnectionHandler` that returns `OutboundSubstreamRequest` with `ReadyUpgrade<StreamProtocol>` and hands back each `FullyNegotiatedOutbound` stream. A hand-encoded FIND_NODE is `[len][08 04 12 20 <32-byte key>]`.

*Observed 2026-10-12 (p2p-network-dev)*

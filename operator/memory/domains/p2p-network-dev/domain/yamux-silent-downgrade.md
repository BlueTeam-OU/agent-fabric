---
role: "p2p-network-dev"
class: domain
description: "Tuning libp2p yamux via any setter silently swaps the muxer to vulnerable yamux 0.12.1, and cargo-deny cannot see that advisory"
tier: 2
knowledge_scope: full
distilled_at: "2026-09-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 2845986aa5033a4d
---

## Tuning libp2p yamux via any setter silently swaps the muxer to vulnerable yamux 0.12.1, and cargo-deny cannot see that advisory

`libp2p-yamux 0.47` depends on **both** yamux 0.12.1 and 0.13.10.
`Config::default()` selects 0.13.10 (patched), which is what
`crates/transport/libp2p/src/runtime.rs` uses. But `Config::set` — reached
by `set_max_num_streams`, `set_receive_window_size`, `set_max_buffer_size`
and `set_window_update_mode` — replaces the config with
`Either::Left(Config012::default())`, silently moving the transport onto
**yamux 0.12.1**, which has a remote-panic DoS (GHSA-vxx9-2994-q338,
malformed Data frame with SYN and len 262145).

`cargo deny check advisories` cannot catch this: RustSec has **no yamux
advisory**, so the GHSA is invisible to the gate. CLAUDE.md §8's claim
that `check_dependencies.sh` enforces "no advisory version" is therefore
stronger than what the tool does for GHSA-only advisories.

**Why:** bounding stream counts and buffers is exactly what CLAUDE.md §6
pushes toward, so the natural next change to yamux config reintroduces a
remote DoS without touching any version number, and nothing fails.

**How to apply:** never call a yamux `Config` setter without checking
which implementation results. Agreed follow-up work, deferred until PR #38
merges: a test that fails if the muxer is ever on 0.12, and reconciling
§8's wording with what RustSec actually covers. hickory-proto alerts on
the same repo are lockfile-only (no `dns` feature, not in the build) and
need no action; the `spikes/spike-002/harness/` lockfile copies are not
production dependencies.

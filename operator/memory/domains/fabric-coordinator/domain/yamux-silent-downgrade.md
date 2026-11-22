---
role: "fabric-coordinator"
class: domain
topic: "yamux-silent-downgrade"
description: "Tuning libp2p yamux via any setter silently swaps the muxer to vulnerable yamux 0.12.1, and cargo-deny cannot see it; InterWeave now guards it with check_yamux_muxer.sh"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 2845986aa5033a4d
  - 93b8a3a634f714fe
---

## Tuning libp2p yamux via any setter silently swaps the muxer to vulnerable yamux 0.12.1, and cargo-deny cannot see it; InterWeave now guards it with check_yamux_muxer.sh

(InterWeave repository, checked on its origin/main 2026-10-11.) `libp2p-yamux 0.47` depends on both yamux 0.12.1 and 0.13.10. `Config::default()` selects 0.13.10 (patched), which is what the transport uses: `crates/transport/libp2p/src/runtime/mod.rs` (the old single `runtime.rs` became a `runtime/` module) passes `yamux::Config::default` to the swarm builder, as do the drivers beside it and the tests. But `Config::set` (reached by `set_max_num_streams`, `set_receive_window_size`, `set_max_buffer_size`, `set_window_update_mode`) replaces the config with `Either::Left(Config012::default())`, silently moving the transport onto yamux 0.12.1, which has a remote-panic DoS (GHSA-vxx9-2994-q338).

`cargo deny check advisories` cannot catch this: RustSec has no yamux advisory, so the GHSA is invisible to the gate.

**The follow-up is done:** `tools/checks/check_yamux_muxer.sh` (with `tools/checks/test_check_yamux_muxer.sh`) is the guard, and InterWeave's CLAUDE.md names "THE RUSTSEC/GHSA GAP" in its dependency section instead of claiming the dependency check covers every advisory. Its tests (`crates/transport/libp2p/tests/root_funnel.rs`) say why they call only default configurations.

**Why it matters:** bounding stream counts and buffers is exactly what that CLAUDE.md pushes toward, so the natural next change to yamux config reintroduces a remote DoS without touching any version number. **How to apply:** never call a yamux `Config` setter without running the guard and checking which implementation results. hickory-proto alerts on the same repo are lockfile-only and need no action; `spikes/spike-002/harness/` lockfile copies are not production dependencies.

*Observed 2026-10-11 (fabric-coordinator)*

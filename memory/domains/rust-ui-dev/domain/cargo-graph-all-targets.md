---
role: "rust-ui-dev"
class: domain
topic: "cargo-graph-all-targets"
description: "Choosing a GUI backend crate set -- Cargo resolves every target's cfg-gated deps, so measure candidates in a scratch copy under cargo deny"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 51a31e484cc1f041
---

## Choosing a GUI backend crate set -- Cargo resolves every target's cfg-gated deps, so measure candidates in a scratch copy under cargo deny

Cargo's lockfile is target-independent: a dependency gated to a platform you never build
must still resolve. i-slint-backend-winit 1.18.1 pulls the skia renderer under
cfg(apple, not macos), whose js-sys requirement conflicted with an exact wasm-only pin from
libp2p -- every winit renderer failed to resolve on Linux. So:
- measure each candidate feature set in a scratch copy of the workspace (never the tree),
  under the project's cargo deny, and report package counts, licence and advisory deltas;
- a conflict between two inert-at-runtime pins is solved by patching the smallest crate at
  the conflict under third_party, not by a second workspace;
- cargo deny's [graph] targets restricts the licence review to the targets built, which keeps
  Windows-only licences (e.g. BSL-1.0 via a clipboard crate) out until that platform is decided.
For a Slint Linux client the measured smallest graph was winit + renderer-software +
accessibility (no GL, no C++ build, same AT-SPI adapter).

*Observed 2026-10-15 (rust-ui-dev)*

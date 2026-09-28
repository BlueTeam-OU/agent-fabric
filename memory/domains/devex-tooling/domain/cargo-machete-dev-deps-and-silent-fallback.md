---
role: "devex-tooling"
class: domain
topic: "cargo-machete-dev-deps-and-silent-fallback"
description: "cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first"
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 6ff0a1f7d20a2db7
---

## cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first

Measured 2026-09-28 on InterWeave 07b5d4bd with cargo-machete 0.9.2:

- The default (text-grep) mode does not judge `[dev-dependencies]` at all:
  2 hits by default, 4 with `--with-metadata`; the 2 extra were real unused
  dev-deps. Sandbox control: a lone unused dev-dep → default exit 0,
  `--with-metadata` exit 1.
- `--with-metadata` exits **0 with no message** when cargo's metadata fails
  (a missing path dep; a registry dep unresolvable offline). A guard must run
  full `cargo metadata --locked` itself first and exit 2 if it fails.
  `--no-deps` does not prove it: it lists members without resolving.
- Pass the workspace members' dirs as paths to scope out spikes/vendored
  crates instead of ignore entries.

Guard: InterWeave `tools/checks/check_unused_dependencies.sh` (#142, 5e117d99).
Open thread: #142 is a draft integration PR awaiting p2p-network-dev-01's
pedantic (719 sites) + 4 manifest fixes (REQUEST 01a0e7db, seq 8551).

*Observed 2026-09-28 (devex-tooling)*

---
role: "devex-tooling"
class: domain
topic: "cargo-machete-dev-deps-and-silent-fallback"
description: "cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 6ff0a1f7d20a2db7
  - b77804dde7bfb6bc
---

## cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first

Measured 2026-09-28 on InterWeave 07b5d4bd with cargo-machete 0.9.2:

- The default (text-grep) mode does not judge `[dev-dependencies]` at all:
  2 hits by default, 4 with `--with-metadata`; the 2 extra were real unused
  dev-deps. Sandbox control: a lone unused dev-dep → default exit 0,
  `--with-metadata` exit 1.
- `--with-metadata` exits **0** when cargo's metadata fails for a crate (a
  missing path dep; a registry dep unresolvable offline; a non-member under the
  workspace root): it prints `error when handling <manifest>` on STDERR, calls
  the crate clean, skips it. A guard needs both: full `cargo metadata --locked`
  first (exit 2 on failure; `--no-deps` proves nothing), and a grep of machete's
  stderr for `^error when handling` (exit 2).
- A root package maps to "." and machete walks recursively: refuse it.
- Pass the workspace members' dirs as paths to scope out spikes/vendored
  crates instead of ignore entries.

Guard: InterWeave `tools/checks/check_unused_dependencies.sh` (#142, 5e117d99).
#142 MERGED 2026-09-28 14:08Z (e5807d99): guard + pedantic + toolchain 1.98.1,
p2p-network-dev-01's 17-commit supply folded. Review P2 was a self-test that
could not catch losing the member filter (sandbox .packages held only members);
fixed with a [patch]ed non-member that has its own [workspace] table.
Next: architect-cto-01 Stage 13 D1 (verify_fixture_vectors ipc-v2-length-prefix-v1)
onto their docs/stage-13-opening branch once pushed; D2-D5 onto p2p's batches.

*Observed 2026-09-28 (devex-tooling)*

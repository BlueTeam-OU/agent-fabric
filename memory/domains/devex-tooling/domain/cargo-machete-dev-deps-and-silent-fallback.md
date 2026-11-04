---
role: "devex-tooling"
class: domain
topic: "cargo-machete-dev-deps-and-silent-fallback"
description: "cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 4378f4156eb9254f
  - 6ff0a1f7d20a2db7
  - b77804dde7bfb6bc
---

## cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first

Measured 2026-09-28 on InterWeave 07b5d4bd with cargo-machete 0.9.2; re-checked against InterWeave origin/main 2026-10-11 (the guard's header still states each point below):

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

Guard: `tools/checks/check_unused_dependencies.sh` in the InterWeave repository (not agent-fabric), added by InterWeave #142 (merged 2026-09-28); its self-test is `test_check_unused_dependencies.sh` beside it. The #142 review's P2 was a self-test that could not catch losing the member filter (the sandbox's .packages held only members); fixed with a [patch]ed non-member that has its own [workspace] table.

*Observed 2026-10-11 (devex-tooling)*

*Observed 2026-10-11 (devex-tooling)*

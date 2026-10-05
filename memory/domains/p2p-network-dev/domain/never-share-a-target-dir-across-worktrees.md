---
role: "p2p-network-dev"
class: domain
topic: "never-share-a-target-dir-across-worktrees"
description: "A worktree of main built with the repo's CARGO_TARGET_DIR overwrote workspace-member artifacts; the branch's next full CI failed to compile on a constant main lacked"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 7252d884d60f556b
---

## A worktree of main built with the repo's CARGO_TARGET_DIR overwrote workspace-member artifacts; the branch's next full CI failed to compile on a constant main lacked

To compare a flake between the branch and main (#147, 2026-09-29), I
built a detached worktree of `origin/main` with
`CARGO_TARGET_DIR=<the repo's target>`. The next `cargo xtask ci` on the
branch failed compiling ipc-protocol with `unresolved import
MAX_CLIENT_KIND_CHARS` ("a similar name exists: MAX_CLIENT_KIND_BYTES",
main's name). A plain `cargo build -p` did not reproduce it, and
`cargo clean -p` of the two packages cleared it.

**Why:** cargo's metadata hash for a workspace member leaves out its
path, so two checkouts of one workspace in one target dir write the
same artifact names. The fingerprint did not always notice.

**How to apply:** give a comparison worktree its own target dir, or
none, and accept the rebuild. If a shared one was used, `cargo clean -p`
the packages that differ before trusting the next run. A compile error
naming the other tree's identifiers is this, not the code.

*Observed 2026-09-29 (p2p-network-dev)*

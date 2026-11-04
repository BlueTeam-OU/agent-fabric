---
role: "rust-services-dev"
class: domain
topic: "mutation-restore-mtime-stale-build"
description: "restoring a file from a backup after a mutation test leaves cargo's mutated build in place; touch the file before the next run"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - a54ccd009da24155
---

## restoring a file from a backup after a mutation test leaves cargo's mutated build in place; touch the file before the next run

When a control mutates a source file and restores it with `cp f f.bak; sed -i …; cargo test; mv f.bak f`, the restored file's mtime is the copy's. That is *older* than the mutated build. Cargo's fingerprint compares mtimes, so the next `cargo test` reuses the mutated binary and reports the mutation's result as the real code's.

Seen 2026-10-20 in InterWeave j55, `apps/claude-channel/tests/host_line.rs`. The "bounded" run after the control showed the control's 200 MB growth. After `touch` it showed 1.1 MB.

**Why:** a stale build makes a passing fix look broken, or worse, a broken one look fixed.

**How to apply:** after restoring a mutated file, `touch` it, or mutate with `git stash` or a reversible `sed` instead of `cp`/`mv`. Check that the next run shows `Compiling <crate>`.

*Observed 2026-10-20 (rust-services-dev)*

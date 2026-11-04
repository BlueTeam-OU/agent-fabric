---
role: "fabric-coordinator"
class: rationale
topic: "no-shared-cargo-target"
description: "a fleet-wide shared CARGO_TARGET_DIR (one per login) is rejected for disk: InterWeave binaries bake CARGO_MANIFEST_DIR; clean on job switch instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - df13d91a44fe3e11
---

## a fleet-wide shared CARGO_TARGET_DIR (one per login) is rejected for disk: InterWeave binaries bake CARGO_MANIFEST_DIR; clean on job switch instead

2026-10-21: /home filled twice in one day, and the owner added 100G. I proposed one CARGO_TARGET_DIR per login, and then withdrew it before building it.

InterWeave binaries, xtask among them, bake in `env!("CARGO_MANIFEST_DIR")`. Cargo does not rebuild when another worktree with the same sources shares the target, so the binaries run with the first worktree's paths. When that worktree was deleted on 2026-10-07, all 31 xtask checks failed with "could not be started" (rust-ui-dev's slice shared-target-worktree).

**Why:** reading a project's own memory before a fleet-wide build change caught a breakage that the documentation would not have shown.

**How to apply:** the fix the owner approved, and the one that went ahead, is "fabric-jobs switch cleans the left job's worktree targets", REQUEST 01a15b7f to python-dev-03 (its job j75). The ADR-037 rule 10 amendment is mine to write. Other disk levers (debuginfo, incremental, profiles) are InterWeave's own decision, for architect-cto. Related: [[home-full-cargo-targets]].

*References: home-full-cargo-targets*

*Observed 2026-10-20 (fabric-coordinator)*

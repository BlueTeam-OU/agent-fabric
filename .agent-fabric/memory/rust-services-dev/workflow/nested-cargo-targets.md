---
role: "rust-services-dev"
class: workflow
topic: "nested-cargo-targets"
description: "freeing disk — InterWeave spikes keep their own cargo targets that ~/projects/*/target misses"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 16a7f038e623ea8d
---

## freeing disk — InterWeave spikes keep their own cargo targets that ~/projects/*/target misses

InterWeave worktrees hold a separate cargo target per spike
(`spikes/*/harness/target`, `spikes/*/phase-b/node/target`, …), which the
`du -sh ~/projects/*/target` glob in a disk request does not see. On
2026-11-10 (j82) 20 of them across the j75/j79/j80/j81 worktrees held
5.0G after the top-level j80 target (34.1 GiB) was already cleaned.

**How to apply:** when asked to free target dirs, find every cargo cache,
not the glob: `find ~ -xdev -type d -name target -prune -exec test -f
{}/CACHEDIR.TAG \; -print`, check no cargo/rustc of yours is running,
then remove. See [[interweave-ci-target-size]].

*References: interweave-ci-target-size*

*Anchors: `interweave:spikes/spike-004/harness/Cargo.toml::[package]`*

*Observed 2026-11-10 (rust-services-dev)*

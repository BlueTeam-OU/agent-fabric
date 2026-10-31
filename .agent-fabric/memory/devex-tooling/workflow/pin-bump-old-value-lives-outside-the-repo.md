---
role: "devex-tooling"
class: workflow
topic: "pin-bump-old-value-lives-outside-the-repo"
description: "a version pin bump (toolchain, interpreter, tool) is unfinished until the old value is grepped outside the repo: agent-fabric projects/registry.json rows and other roles' committed memory slices"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6c7942d98cdab863
---

## a version pin bump (toolchain, interpreter, tool) is unfinished until the old value is grepped outside the repo: agent-fabric projects/registry.json rows and other roles' committed memory slices

Three pin bumps in 2026-W43 left the old value stated as current somewhere the bumping repo's
own grep never reaches:

- the InterWeave Rust toolchain bump (1.98.1 → 1.99.1). agent-fabric `projects/registry.json`
  still proved and installed cargo-ndk and the Android rust-std on 1.98.1. That needed a
  patch to fabric-coordinator after the merge.
- the same bump made p2p-network-dev's committed workflow slice wrong in the present tense.
  It still gave the pin, a lint rule and the local gate flags for 1.98. The blind review
  found it by grepping the old version at the head.
- the fabric-python move to 3.14. Three `projects/registry.json` rows still said 3.13, and
  the re-review found them.

**How to apply:** before a bump PR is called done, grep the old value (bare and in its
common spellings) across the repo, agent-fabric's `projects/registry.json` and `runtime/`, and
every `.agent-fabric/memory/` and `memory/domains/` slice. Route each hit to its owner: a
patch to fabric-coordinator for the control plane, an OBSERVATION naming the slice for a
role's memory, and a `merge_target` correction for your own drained slice. Leave worked
examples that only quote a version. This generalizes the slice `iw-cargo-tool-pins-live-in-two-places`
from cargo tools to any pin.

*Anchors: `projects/registry.json::rust-std-aarch64-linux-android`*

*Observed 2026-10-25 (devex-tooling)*

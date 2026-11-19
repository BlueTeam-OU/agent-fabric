---
role: "python-dev"
class: workflow
topic: "correction-title-is-description-not-clipped"
description: "A correction memory's description must equal its merge_target in full; a 100-char clip is refused by the drain as a prefix title"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b856a050600cbe1d
---

## A correction memory's description must equal its merge_target in full; a 100-char clip is refused by the drain as a prefix title

The drain (tools/fabric/assembler/shapes.py) takes a correction's title from the memory's `description`. A description clipped at 100 characters while `merge_target` holds the longer heading is refused ("correction title is a prefix of the heading it replaces"), and the slice is held out of the drain (j123, 2026-11-08).

**Why:** the j73 re-check memories were written with a clipped description; seven were affected, all fixed together.
**How to apply:** write the description as the whole merge_target heading. When a drain says a merge_target names no section, the section was usually already filed as its own topic: drop the merge_target (j124). Check origin/main's slice headings first.

*Anchors: `tools/fabric/assembler/shapes.py::strict prefix`*

*Observed 2026-11-08 (python-dev)*

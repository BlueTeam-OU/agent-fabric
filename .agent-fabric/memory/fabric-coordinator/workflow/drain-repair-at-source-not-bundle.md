---
role: "fabric-coordinator"
class: workflow
topic: "drain-repair-at-source-not-bundle"
description: "a drain repair made only in the harvested bundles is undone by the next --all harvest; fix the memories at source, re-apply the bundle fixer, and diff anchors per slice following renames"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 28b8eadef6936d27
---

## a drain repair made only in the harvested bundles is undone by the next --all harvest; fix the memories at source, re-apply the bundle fixer, and diff anchors per slice following renames

2026-11-08, agent-fabric #510 (drain 2026-11-08) round 1, F1: on 2026-10-31, the anchor repair (cec12748) was made with fix_anchors.py
inside the bundles only. The harvest always runs `--all`, so the next drain read the authors' unchanged memories. The assembler then
wrote 19 old, unresolving anchors back over the repaired corpus. Round 2 found one more: a slice that moved (workflow.md into
workflow/<topic>.md) was invisible to my per-path anchor comparison.

**Why:** the bundle is a copy of each author's memory, and every harvest rebuilds it from the source.
**How to apply:** after any bundle repair, send each author the exact rewrites to make in their own memories (or make them in
my own), and re-run the fixer on every later drain until the source is clean. Before committing a drain, compare anchors per
slice against main with `git diff -M`, so moved files are compared with their origin. An assembler guard that keeps a resolving
corpus anchor over an unresolving incoming one is job j663. Related: [[drain-anchor-repair-f1f2]], [[j650-drain-2026-11-08]].

*References: drain-anchor-repair-f1f2, j650-drain-2026-11-08*

*Anchors: `tools/fabric/assemble.py::--bundle`, `tools/fabric/anchors.py::def split`*

*Observed 2026-11-08 (fabric-coordinator)*

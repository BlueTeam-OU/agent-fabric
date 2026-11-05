---
role: "fabric-coordinator"
class: workflow
topic: "drain-multi-pass-procedure"
description: "A fleet drain runs in four passes: one that collects every collision, the real run with the owner's decisions, a second full pass, then an index-only run per project; and the bundles are copied out of the scratchpad"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d5e243b81125515f
---

## A fleet drain runs in four passes: one that collects every collision, the real run with the owner's decisions, a second full pass, then an index-only run per project; and the bundles are copied out of the scratchpad

2026-10-31, the drain for j279 (83 bundles, 13 projects, fabric commit c298f65e):

1. **Collect every collision first.** `assemble.py` stops at the first collision and writes nothing for that bundle. Run every bundle, log the bundles that hit SUPERSEDING? and carry on. That gives the whole list for one question to the owner, instead of one re-run per collision. This drain had 14, and in every one the incoming memory was older than the corpus section: memories `--all` re-harvested, already superseded. The owner dropped all 14. `--hold` must name a slice in that bundle's own claims ("names no slice of this drain" otherwise), so it goes on that one bundle, never on every run. Collision decisions are per bundle too: one file per bundle, keyed `<role>/<class>:<topic>#<heading>@<evidence>`.
2. **The real run**: project bundles first, agent-fabric's last ([[drain-fabric-project-bundle-last]]), stamp fixed.
3. **A second full pass** with the same stamp left the fabric tree byte-identical (stage pass 1 to see that). It can raise a new collision of its own: pass 1's newer text now sits in the corpus. That run writes nothing, so pass 1's result stands.
4. **Project indexes still drift** for roles that have no bundle in that project. Fix them with the index-only run ([[index-only-regeneration]]) on every project copy, same stamp, so it merges into today's report. Then lint with `--no-siblings --working-copy <id>=<dir>` for each copy: what is left belongs to the projects (InterWeave's over-budget slices; projects that have no taxonomy).

Re-running a single bundle after the full pass is not safe: two chained merge_targets (memory A replaced the original, memory B replaced A) appended A's section a second time. Revert anything such a run changes.

The bundles live in the session scratchpad, which is lost when the session ends. Copy them, the decision files and the runner to `~/drain/<stamp>/` (mode 0700), so each project's own session can assemble its half later.

**Acceptance for an assembler or drain-tool PR** (reflection 2026-W44). Green synthetic tests and CI are not enough. Only the coordinator holds the harvested bundles, so the coordinator replays the last real drain on the PR's head: pass 1, then pass 2 over pass 1's tree, with index-only runs between, and a diff of the two. In W44 three defects appeared only on that replay, after the tests had passed: a rule firing on one project, a link pointing to the wrong place, and a stamp re-carrying old corrections on a second run (that last one after the PR had merged). Messages: 01a19467-6b52-76f9-b8f0-d786e260db43, 01a1946a-278c-7bff-bd69-6fa6970be803, 01a19471-8a8b-7095-8715-40400a4585a0, 01a19480-b662-7894-9fbe-22be3c85cb9e, 01a1952e-b198-765b-a336-a02c9e58fa9f.

*References: drain-fabric-project-bundle-last, index-only-regeneration*

*Anchors: `tools/fabric/assemble.py::--collision-decisions`, `tools/fabric/assemble.py::--hold`, `tools/fabric/lint.py::--working-copy`*

*Observed 2026-10-31 (fabric-coordinator)*

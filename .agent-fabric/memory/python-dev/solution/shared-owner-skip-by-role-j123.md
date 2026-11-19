---
role: "python-dev"
class: solution
topic: "shared-owner-skip-by-role-j123"
description: "#531 — shared_with kept, unbound owners skipped by role for project classes only; re-review traps, CI rerun, j124(a) is an input gap"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 55c13f3c2e90723b
---

## #531 — shared_with kept, unbound owners skipped by role for project classes only; re-review traps, CI rerun, j124(a) is an input gap

#531 (merged d28708af): assembler `shared_with` stays as recorded; `Run.unindexed_owners` (a set of roles) is skipped in `write_shared` only for `layout.PROJECT_CLASSES`. Keyed by slice it leaked through a `merge_target` move (targets.py carries shared_owners, not a per-slice set); role-wide without the class test it dropped an unbound owner's shared *domain* slice (domain slices are never judged by a taxonomy). `index_role` re-lists every shared slice on disk naming the role, so an unbound owner with an existing directory keeps its entry (pinned by a test).

**Why:** the replay of the 2026-11-08 drain found each.
**How to apply:** a skip that the hold judges per class must test the same class set; mutate by removing each skip and see two or more tests fail.

Traps: (1) the re-review prompt must be the rendered brief verbatim — retyping it once invented diff lines; cut the diff only with a pointer to git. (2) `gh run rerun --failed` after `abandoned` jobs left `ci-ok`/`static`/`reuse` off the head and the PR BLOCKED; rerun the whole run. (3) count rule 1 work commit in agent-fabric, so a python-dev PR at 3 work arms itself at the review gate.

j124(a) (bare anchor kept nothing): an input gap — anchorkeep judges `proj:path` in the checkout beside the tree; the drain's interweave checkout was under wt/, lint got explicit `--working-copy p=path`. Owner decision: assemble takes repeatable `--working-copy <project>=<path>` and hands the map to anchorkeep.

*Anchors: `tools/fabric/assembler/writer.py::unindexed_owners`, `tools/fabric/assembler/intake.py::unindexed_owners`*

*Observed 2026-11-09 (python-dev)*

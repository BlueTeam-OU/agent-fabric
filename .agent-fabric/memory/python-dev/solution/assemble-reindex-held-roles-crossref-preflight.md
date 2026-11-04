---
role: "python-dev"
class: solution
topic: "assemble-reindex-held-roles-crossref-preflight"
description: "assemble.py re-indexes every role dir a project holds (PR 301); a corrupt crossref.json of a dormant role must refuse before any write"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 845c815ecc2a00d5
---

## assemble.py re-indexes every role dir a project holds (PR 301); a corrupt crossref.json of a dormant role must refuse before any write

Since PR #301 (j47) `tools/fabric/assemble.py` calls `index_role` for every dir under `<wc>/.agent-fabric/memory/` (not `shared/`, only role ids), kept out of `run.owning_roles` so the report's `roles` stays the drain's own. Because dormant roles are now read, `read_crossref_index` pre-checks every held role's crossref.json before `write_shared`, exiting with the path (review round 1 P2: a traceback after writes left no report).

**Why:** two drains needed hand re-indexes when another project's bundle wrote a role's domain slices.
**How to apply:** any new read of a per-role file in assemble must be pre-checked before the first write. Open carry: a crossref.json with malformed nested shape (`{"index":{"adr":[1]}}`) still raises AttributeError in `index_role` after writes (pre-existing).

*Anchors: `tools/fabric/assembler/index.py::read_crossref_index`, `tools/fabric/assembler/index.py::roles_with_project_directory`*

*Observed 2026-10-18 (python-dev)*

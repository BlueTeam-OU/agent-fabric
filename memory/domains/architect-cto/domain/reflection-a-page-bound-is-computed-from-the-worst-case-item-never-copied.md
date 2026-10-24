---
role: "architect-cto"
class: domain
topic: "reflection-a-page-bound-is-computed-from-the-worst-case-item-never-copied"
description: "A page or batch bound is computed from the worst-case serialized item against the frame or body ceiling, never copied from a sibling surface whose items are smaller"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - e0c9f803881dd1be
---

## A page or batch bound is computed from the worst-case serialized item against the frame or body ceiling, never copied from a sibling surface whose items are smaller

InterWeave 2026-10-05: my ruling "paged as admin.trust.list (1024
rows)" (01a112c6-81c3); "1024 rows do not fit the IPC body ceiling,
MAX_BODY_BYTES = 131 072" (01a11398-8b4c); DECISION 01a11399-d051: "512
rows a page… 194-byte worst-case row". LOCAL-IPC.md carries the 512-row
bound for that surface only. Beside
[[reflection-a-mirrored-bound-copies-each-dimension]].

*References: reflection-a-mirrored-bound-copies-each-dimension*

*Observed 2026-10-23 (architect-cto)*

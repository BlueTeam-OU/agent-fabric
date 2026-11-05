---
role: "fabric-coordinator"
class: rationale
topic: "harvest-key-pointed-links"
description: "why the harvest's rule-10 keys miss a memory whose [[link]] the assembler pointed, and why the fix is an either-key match, never a link-blind key"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ca5d58b58e10b3e
---

## why the harvest's rule-10 keys miss a memory whose [[link]] the assembler pointed, and why the fix is an either-key match, never a link-blind key

ADR-050 rule 10's keys (tools/fabric/corrections.py) are recorded over text the assembler has already pointed:
applied_key over `rendered` after point_links (assembler/writer.py ~286), replaced_key over a section point_disk_in
may have pointed. The harvest (harvest_memory.py, replaced_by_key / applied_by_key) keys the body as written, so a
memory linking a moved memory's stem is missed: re-harvested, or its original never named for retirement. Measured
2026-11-04: 5 of 59 applied_corrections sections in agent-fabric's corpus carry such a link; 0 elsewhere.

Decided (j400): a defect against memory_key's own contract ("the text the assembler would render"), no ADR change.
The harvest matches on either key — as written, or pointed with the map built from the report's applied_corrections
— with the pointing moved into corrections.py so both sides share one implementation. A link-blind key was rejected:
a correction that changes only a link target would equal its original and be skipped as applied.

Contract: REQUEST 01a1a841-7876 to python-dev-01 (their entry merges; I distribute).

*Observed 2026-11-04 (fabric-coordinator)*

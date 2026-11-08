---
role: "fabric-coordinator"
class: threads
topic: "adr-066-reratify-pending"
description: "ADR-066 merged on main (#497, 2026-11-07) with binding text changed after the owner's acceptance; owner's re-confirmation still owed"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f1dc7ae0481fc651
---

## ADR-066 merged on main (#497, 2026-11-07) with binding text changed after the owner's acceptance; owner's re-confirmation still owed

ADR-066 (review class measured like a classifier) reached main with #497 (merged on head a6644f4e, 2026-11-07). The owner accepted it earlier that day (68db2988), but after that 67bdbcf0 changed §5 rules 4 and 6, and 72231a6a changed rule 7 (a seeded defect's hash coordinates: repository, base sha, head sha, defect id) and §2 rate 2 (a finding's level is its own `Finding:` line's). There is no amendment row and no history note, and the "Ratified" line is unchanged. Both blind reviews (rounds 9 and 10) named this as a risk.

**Why:** a record is accepted only on the owner's word for that text ([[accepted-only-when-on-main]]).
**How to apply:** ask the owner whether the merged text is the one they ratify. If they say no, or they want the change on record, write an amendment under docs/adr/history/ with an Amendments row and a DIGEST bullet ([[gateway-adr-amendment-checklist]]).

*References: accepted-only-when-on-main, gateway-adr-amendment-checklist*

*Observed 2026-11-07 (fabric-coordinator)*

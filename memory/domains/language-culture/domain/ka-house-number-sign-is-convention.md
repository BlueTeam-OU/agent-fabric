---
role: "language-culture"
class: domain
topic: "ka-house-number-sign-is-convention"
description: In a Georgian address № before the house number is convention, not a data defect; the number sign may be stripped, a flat or block marker never
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0bae3995d832f7a2
---

## In a Georgian address № before the house number is convention, not a data defect; the number sign may be stripped, a flat or block marker never

A Georgian writes a house number with the sign № — the public registry
itself does ("ბახტრიონის ქ. №22, ბ. 75") — and a rider types it the same
way into a search field. So №2, N3, N 7 in the data are convention, not
a mapper's error; a regex that wants "starts with a digit" will call
them defects. Which prefixes may be stripped is a language question:
№ (U+2116), N, N., No. and Russian д. ("house") are number signs that
carry nothing; ბ. ("flat"), кв. and к. ("block") are another part of the
address, and stripping them names a different door. In gzapp these lists
stand verbatim in ADR-035 §2.4, named as this role's.

*Observed 2026-10-16 (language-culture)*

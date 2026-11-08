---
role: "language-culture"
class: solution
topic: "carrier-term-ru"
description: "how to say carrier (GZCoord's second delivery route) in ru-RU.json without the brand name"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - db88e91c41bf72de
---

## how to say carrier (GZCoord's second delivery route) in ru-RU.json without the brand name

In the GZCoord dictionary (identities/roles/language-culture/locale/ru/ru-RU.json), "carrier" without a name is rendered "другим путём" (by another route: "оно доставлено другим путём"), not "канал", which already means {channel} (inbox.head, send.would-post), and not "транспорт" (a calque, flagged by the first pass). lint.py refuses the brand name (InterWeave) in the shared file. Commit 1d2c8af5, 2026-11-08.

*Observed 2026-11-08 (language-culture)*

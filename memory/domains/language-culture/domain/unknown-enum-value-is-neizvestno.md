---
role: "language-culture"
class: domain
topic: "unknown-enum-value-is-neizvestno"
description: ru word for a value the build does not know (status, role, model, language, kind) — «Неизвестно», not «Не распознано»
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - c505b08b11a87ed4
---

## ru word for a value the build does not know (status, role, model, language, kind) — «Неизвестно», not «Не распознано»

In a cell, a badge or after "Role:", a non-null value this build does not know is «Неизвестно» in ru-RU, not «Не распознано».

«Не распознано» reads as a failure the merchant must act on (a broken, still-charging campaign, a suspect staff member, a failed language detection, an unverified venue).

One word for both operator.enum.unknown and common.enum.unknown (gzapp #1106); en-US is "Unknown". An absent value gets its own key, «Не указано».

*References: absence-speaks-about-the-record*

*Observed 2026-10-11 (language-culture)*

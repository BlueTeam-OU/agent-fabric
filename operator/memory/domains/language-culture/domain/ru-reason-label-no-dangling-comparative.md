---
role: "language-culture"
class: domain
topic: "ru-reason-label-no-dangling-comparative"
description: "A selection-reason label never states a comparative with no second term; for a replacement the label names the replaced stop, and 'the planned one' has a referent because the passenger is told (ADR-079 s2.5)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - cd1daef6143c356e
---

## A selection-reason label never states a comparative with no second term; for a replacement the label names the replaced stop, and 'the planned one' has a referent because the passenger is told (ADR-079 s2.5)

A selection-reason label states the reason or the replacement, never a bare comparative: "more convenient" reads as "than what?". For official_stop_selected the owner decided (REPLY 01a17155) the label names the replacement, as en-US ("An official stop chosen over the planned one") and ka-GE do. ru-RU is "Выбрана официальная остановка вместо запланированной" ("An official stop chosen instead of the planned one", commit 766da8202 atop ac04728d4). The change leads, as in shifted_* and ka-GE; the lone participle anchors to the mid-sentence "остановка" without repeating the noun. "запланированной", not "намеченной", renders "the planned one". My earlier claim that "the driver never sees the plan, so 'planned' has nothing to point to" was overruled by the owner with the fact that the passenger is told of the new stop (ADR-079 §2.5). The two-participle stack ("выбранная вместо запланированной") was caught by the cold first pass.

*References: copy-names-no-server-set-figure, ru-moving-point-is-mesto-ostanovki*

*Observed 2026-10-25 (language-culture)*

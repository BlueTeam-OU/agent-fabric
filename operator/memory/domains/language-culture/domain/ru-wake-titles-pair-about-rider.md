---
role: "language-culture"
class: domain
topic: "ru-wake-titles-pair-about-rider"
description: "the ru-RU boarding/alighting title pair speaks of the rider: «Скоро посадка» / «Скоро выходить»"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - c4fab6fc44a12c61
---

## the ru-RU boarding/alighting title pair speaks of the rider: «Скоро посадка» / «Скоро выходить»

The ADR-077 notification titles in ru-RU are a pair about the rider: «Скоро посадка» ("boarding soon") and «Скоро выходить» ("your stop soon"; the latter the words of journey.leg-state.alighting). «Маршрутка подъезжает» ("the minibus is arriving") over a body saying «скоро подойдёт» ("will come soon") reads as two different moments. Of a place, «близко» ("near"), not «скоро» ("soon"). No text says «следующая остановка» ("next stop"): the wake may come more than one stop ahead (ADR-077 §2.2). Commit 4f3136f25 (j68).

**Why:** locale-worker's cold read, 2026-10-19; the requester's amendment 01a155a6.
**How to apply:** new boarding/alighting notifications keep this pair and never promise the "next" stop.

*Observed 2026-11-09 (language-culture)*

---
role: "language-culture"
class: domain
topic: "ru-marshrut-is-the-line-not-the-trip"
description: "In Russian transit copy «маршрут» is a transit line/route, never the rider's trip; the trip is «поездка», the endpoint pair «откуда и куда»"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - e44dc90d54b94245
---

## In Russian transit copy «маршрут» is a transit line/route, never the rider's trip; the trip is «поездка», the endpoint pair «откуда и куда»

To a rider, «маршрут» is what the minibus or bus plate says ("route 37"). Copy that calls the person's own trip a маршрут («по выбранному маршруту» in journey.plan-hint, 2026-09-20) reads as choosing a transit line — and in that phase (JourneyPhase.idle) no route exists yet, only two points. The ge holder found the same defect in ka-GE independently (მარშრუტი is also the everyday word for a line). Rule: «маршрут» only for a transit line; the person's trip is «поездка», the chosen pair «откуда и куда» / «выбранные точки». The stronger home is a rule in product/i18n/glossary/ru-RU.json, absent on origin/main as of 2026-10-15 — to be proposed as its own piece of work.

*References: ka-recurring-defect-families*

*Observed 2026-10-15 (language-culture)*

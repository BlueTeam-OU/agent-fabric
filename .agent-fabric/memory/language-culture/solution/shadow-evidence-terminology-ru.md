---
role: "language-culture"
class: solution
topic: "shadow-evidence-terminology-ru"
description: "Russian terms for gzapp's shadow-results page: vehicle, stopping point, feasibility policy, dataset, current system, new stop planning"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 94f3c2e1f7877941
---

## Russian terms for gzapp's shadow-results page: vehicle, stopping point, feasibility policy, dataset, current system, new stop planning

Russian terms for gzapp's "stop planning: shadow results" page
(`admin.stops.shadow-evidence.*`, 56 keys, en-US cafc3131a, j93), derived from
existing ru-RU strings: vehicle → "машина" (concrete; a list title is "Транспорт"),
pick-up/drop-off → "посадка"/"высадка", stop → "остановка", stopping point → "точка
остановки", fixed stop → "официальная остановка" (so choice.* contrasts an official
stop with a point along the route; plain "не остановка" reads as "not a stop at all"),
stopping mode → "режим остановок", feasibility
policy → "политика выполнимости", dataset → "расписание"; the requester's terms: "the
current system" (live matcher) → "текущая система", "the new stop planning"
(consolidator) → "новое планирование остановок". Count keys without plural slots use a
plural-free form ("Оценок: {count}"). The noun "count(s)" (tallies of pick-ups/drop-offs in a
cell) → "количество"/"количества", never "значение" ("значение" = value, a shift; sibling ka-GE
holds "რაოდენობა" = quantity).

*Anchors: `gzapp:product/i18n/ru-RU.json::admin.stops.shadow-evidence.title`*

*Observed 2026-10-26 (language-culture)*

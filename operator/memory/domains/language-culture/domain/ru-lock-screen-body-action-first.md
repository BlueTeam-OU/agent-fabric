---
role: "language-culture"
class: domain
topic: "ru-lock-screen-body-action-first"
description: "ru-RU on-request copy: the action in the first words, assert nothing, since the flag is a union over trips"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - b60374b5503078ff
---

## ru-RU on-request copy: the action in the first words, assert nothing, since the flag is a union over trips

ru-RU variants of the on-request notification and hint: the action comes in the first words (the preview cuts the tail, and the title may show alone), and the text only asks. It does not call the stop on-request and does not say «может проехать мимо» ("may pass by"): the on_request flag is a union over all of a stop's trips, so for this route it may be untrue (ADR-077 A 2026-10-20). The timing («когда подойдёт», "when it comes") goes in the title, or a lone title reads as "now"; «ваша маршрутка» ("your minibus"), or it reads as any minibus. The stop name follows «на остановке» ("at the stop"), so its grammatical case never breaks. Keys: journey.wake.*-on-request, journey.now.on-request-* (commits 000abf515, ef2c40df9).

**Why:** architect-cto's decision of 2026-10-20, and locale-worker's cold reads in j69–j71.
**How to apply:** any new on-request text asks for the action and asserts nothing.

*Observed 2026-11-09 (language-culture)*

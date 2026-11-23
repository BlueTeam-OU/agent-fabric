---
role: "language-culture"
class: domain
topic: "ru-call-sign-pozyvnoy"
description: "ru-RU for the journey call sign (ADR-078) and a silent phone: «позывной», «не на связи»"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - b3d3a3504c51759f
---

## ru-RU for the journey call sign (ADR-078) and a silent phone: «позывной», «не на связи»

The journey call sign (ADR-078, four characters such as K7MX) is «позывной» in Russian: a name someone calls out, not «код» ("code") nor «пароль» ("password"). A rider's silent phone is «Телефон пассажира не на связи» ("the rider's phone is out of contact"): one phrase for the band, the «с {time}» ("since {time}") line and the notification title. «Может не видеть телефон» ("may not see the phone") reads literally, since the phone is in the rider's hand. Do not narrow the cause to «пропала связь» ("signal lost"): the battery may be flat or the app closed. Commit acbbdeb50, gzapp#1119.

*Observed 2026-11-09 (language-culture)*

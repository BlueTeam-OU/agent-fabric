---
role: "language-culture"
class: domain
topic: "ru-pronoun-antecedent-check"
description: "In a Russian rendering of English, check every pronoun and past-tense verb for gender and for the nearest noun — English it/they carry no gender, and a past-tense verb needs a gendered subject"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1c1c9aefdf30fd92
---

## In a Russian rendering of English, check every pronoun and past-tense verb for gender and for the nearest noun — English it/they carry no gender, and a past-tense verb needs a gendered subject

English "it", "they/them", "their" carry no gender; a Russian pronoun agrees in gender and binds to the nearest matching noun. Twice in 2026-W42 this produced an error: in the charter "Намерение … она" (intention is neuter; fixed in ef0e1c0f), and in a driver string where "его" after "Телефон пассажира" read as the phone, not the passenger (gzapp 2df3bac43; the noun was repeated). The same rule governs the past-tense verb: Russian past singular agrees in gender with its subject, so it cannot stand when the subject is a genderless placeholder ({vehicle}, {id}). In admin.operations.positions.stopped-reporting (gzapp #1164, 412b9f6c2) the present tense "{vehicle} больше не передаёт местоположение" replaces a past form, so it reads correctly for any label or id. The calque passes the second pass and only a Russian reader sees it. On the first pass ask of every pronoun its gender and which nearest noun the reader binds it to; repeat the noun if wrong; prefer present or impersonal form over past singular for a placeholder subject.

*References: first-pass-scope-to-changed-text*

*Observed 2026-10-25 (language-culture)*

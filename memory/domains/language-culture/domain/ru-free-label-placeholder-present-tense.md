---
role: "language-culture"
class: domain
topic: "ru-free-label-placeholder-present-tense"
description: "a placeholder holding a free label ({vehicle} = label ?? id): a present-tense verb, no gender, and no «Машина {vehicle}»"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 7f754b3859e39da7
---

## a placeholder holding a free label ({vehicle} = label ?? id): a present-tense verb, no gender, and no «Машина {vehicle}»

When a placeholder holds an operator's free label or a vehicle number (in gzapp `{vehicle}` = `label ?? physical_vehicle_id`, and `physical_vehicle_id` is a plate or fleet number, not a UUID), the grammatical gender of what is substituted is unknown. A past-tense verb («перестала/перестал», "stopped", feminine/masculine) does not fit, and «Машина {vehicle}» ("Vehicle {vehicle}") gives «Машина Автобус 10» ("Vehicle Bus 10"). The answer is the present tense, which has no gender: «{vehicle} больше не передаёт местоположение — карточка закрылась» ("{vehicle} no longer sends its location — the card has closed") (#1164, commit 412b9f6c2).

**Why:** a cold read by locale-worker confirmed that the genderless wording reads correctly with any label.
**How to apply:** before translating a string with a placeholder, find out where its value comes from; if it is free text, build the phrase so that nothing agrees with the placeholder in gender.

*Observed 2026-11-09 (language-culture)*

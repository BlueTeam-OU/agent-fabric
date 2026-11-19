---
role: "language-culture"
class: domain
topic: "ka-inanimate-plural-singular-verb"
description: when an animate noun is replaced by an inanimate one, recheck the verb agreement
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 34d33443e8088a73
---

## when an animate noun is replaced by an inanimate one, recheck the verb agreement

In Georgian an inanimate plural subject takes a singular verb ("ანგარიშები დასახელებულია", accounts
are named), an animate one a plural verb ("მფლობელები არიან დასახელებულნი"). Swapping the noun
(holders -> accounts) leaves the rest of the sentence alone and silently breaks agreement; a diff
review misses it when the verb is not on the changed line. Georgian legal-expert charter L20-21,
REPLY 01a1450d (2026-10-16), found by the cold reader in the first pass. How to apply: on a term
swap, reread the whole sentence: verb, participle, pronoun.

*Observed 2026-11-09 (language-culture)*

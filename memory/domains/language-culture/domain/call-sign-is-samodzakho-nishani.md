---
role: "language-culture"
class: domain
topic: "call-sign-is-samodzakho-nishani"
description: "ADR-078 call sign in Georgian: სამოძახო ნიშანი, the driver is told დაიძახეთ; \"phone not responding\" reads as an unanswered call (dba5b7207, 2026-10-16)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - c9d036c13dd0aec9
---

## ADR-078 call sign in Georgian: სამოძახო ნიშანი, the driver is told დაიძახეთ; "phone not responding" reads as an unanswered call (dba5b7207, 2026-10-16)

In ka-GE, the ADR-078 call sign is "სამოძახო ნიშანი". The driver is told "ხმამაღლა დაიძახეთ", the verb used for calling out a stop on a marshrutka (#1119, dba5b7207). A cold reader proposed "საცნობი ნიშანი". I rejected it because it reads as an identifying mark, that is, an identifier, which ADR-078 forbids. ru-RU uses позывной.

"Phone not responding" is not "ტელეფონი არ პასუხობს", because a Georgian reader takes that as an unanswered call. Use "კავშირზე არ არის" or "კავშირი გაწყდა {time}-ზე".

Why: one term is shared by two apps, a notification and the screen reader. A new key with another word splits the term.
How to apply: for any new call-sign key, grep ka-GE.json for სამოძახო and use the same form. A glossary rule may follow.

*References: glossary-rules-are-enforceable*

*Observed 2026-10-16 (language-culture)*

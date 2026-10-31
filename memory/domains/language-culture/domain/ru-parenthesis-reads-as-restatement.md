---
role: "language-culture"
class: domain
topic: "ru-parenthesis-reads-as-restatement"
description: "A Russian parenthesis \"(тот, что …)\" reads as \"that is\"; put a narrower case in its own sentence"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 9c7ef2ce22862ed1
---

## A Russian parenthesis "(тот, что …)" reads as "that is"; put a narrower case in its own sentence

In Russian, a parenthesis like "(тот, что …)" reads as "that is", so an English parenthesis naming a narrower case gets read as a restatement, and the general/specific distinction is lost. It was exactly the point of #283 r6 F1: "addressed to you" is wider than TO. Render the narrower case as its own sentence after the main clause (e4275143, 2026-10-16).

*References: charter-ru-reuse-existing-phrasing*

*Observed 2026-10-16 (language-culture)*

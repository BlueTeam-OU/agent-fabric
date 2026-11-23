---
role: "language-culture"
class: domain
topic: "legal-condition-sentence-stays-whole"
description: "in legal copy, do not split a \"Where X, A, and B\" sentence; B leaves the condition. A doubled \"where\" can become \"if\""
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: blueteam.ee
    working_copy: blueteam.ee
derived_from:
  - d8e8358b759df678
---

## in legal copy, do not split a "Where X, A, and B" sentence; B leaves the condition. A doubled "where" can become "if"

In legal-register copy, a sentence of the form "Where X, A, and B" keeps B under the condition X. Splitting it ("Where X, A. B.") makes B unconditional, so it changes legal effect. Found on the blueteam.ee disclaimer, Scope paragraph, 1b2c398 line 55 (REPLY 01a1c70c-d95c, 2026-11-11). For readability, change a doubled "where ... where ..." instead: the inner conditional "where" becomes "if", which states the same condition and no "only". Offer it as a span, and say it touches the clause it sits in, so the owner can send it to legal.

**Why:** shortening sentences is the default global-English move, and in a conditional legal sentence it moves the obligation outside its condition.
**How to apply:** before splitting any long sentence in legal or specification prose, check whether it opens with a condition ("Where", "If", "Unless"). If it does, keep it whole. Related: [[keep-else-whole]], [[quote-a-condition-verbatim]].

*References: keep-else-whole, quote-a-condition-verbatim*

*Observed 2026-11-10 (language-culture)*

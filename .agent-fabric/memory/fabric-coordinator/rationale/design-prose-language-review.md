---
role: "fabric-coordinator"
class: rationale
topic: "design-prose-language-review"
description: "Owner 2026-10-16 — language-culture reviews the English of every InterWeave design/ spec; behaviour stays with the author"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0a7bdaa2101ca3ba
---

## Owner 2026-10-16 — language-culture reviews the English of every InterWeave design/ spec; behaviour stays with the author

The owner, 2026-10-16: the English of a specification goes to language-culture (language-culture-en for InterWeave), not to the expert who wrote it. ux-designer-01 had been sent #286's review findings, and the owner wanted the language side handled by language-culture.

What is now written: InterWeave `.agent-fabric/roles/language-culture.md` and `ux-designer.md` (commit 26524c45 on #286), and the taxonomy binds `design/` to both roles. language-culture-en reviews clarity, terms and misreadable words, and finalises the strings a spec names. A finding that changes what the app does (#286 F1, F2, R1) stays with the spec's author.

**Why:** a designer's spec is read by builders; its prose quality is a language job.
**How to apply:** for every new design/ spec PR, send a language review to language-culture-en beside the blind review. Route a finding by whether it changes behaviour (author) or wording (language-culture). For a different project, ask the owner before applying the same rule.

*Observed 2026-10-16 (fabric-coordinator)*

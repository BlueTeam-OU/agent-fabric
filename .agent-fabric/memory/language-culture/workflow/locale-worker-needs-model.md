---
role: "language-culture"
class: workflow
topic: "locale-worker-needs-model"
description: "a locale-worker dispatch needs model (opus); without it the hook refuses it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1dcd3ec000ce1a4f
---

## a locale-worker dispatch needs model (opus); without it the hook refuses it

`locale-worker`-ის Agent-გამოძახება `model`-ის გარეშე PreToolUse ჰუკმა უარყო
(„locale-worker dispatch has no model set … opus is the design“, ADR-027).
იზოლაცია არ სჭირდება; `model: opus` საკმარისია (j72, 2026-10-16).

**Why:** უცნობი მოდელი სესიის მოდელს შემთხვევით იღებს; ენობრივი განსჯა premium-ია.
**How to apply:** მუშაკს ყოველთვის `subagent_type: locale-worker, model: opus`-ით უშვებ.

### English
A locale-worker Agent dispatch without `model` is refused by the PreToolUse
hook (ADR-027); `model: opus`, no isolation, is the accepted shape (j72, 2026-10-16).

*Observed 2026-11-09 (language-culture)*

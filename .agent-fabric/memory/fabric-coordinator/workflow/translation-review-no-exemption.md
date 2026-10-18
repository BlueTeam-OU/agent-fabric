---
role: "fabric-coordinator"
class: workflow
topic: "translation-review-no-exemption"
description: "Never waive language-culture's two-pass review of a translation, even for one clause; the owner kept ADR-027 rule 11 as written (2026-10-16)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1d87af766da34af9
---

## Never waive language-culture's two-pass review of a translation, even for one clause; the owner kept ADR-027 rule 11 as written (2026-10-16)

Every change to a translated charter goes through `language-culture-<suffix>`'s two passes (ADR-027 §5 rule 3 and rule 11) before its pull request, however small: one clause, one word, a re-render after a source fix.

On #283 I told legal-expert-ge that a one-clause re-render needed "no new round" twice (7e8d63e7, f184097e). #288's round-4 review found that this broke rule 11. The owner said: "stop granting it, keep the rule."

**Why:** the rule has no size threshold, and an exemption I grant in a message is invisible to the record and to the next reviewer.
**How to apply:** a re-render request to a locale holder always says that language-culture reviews it in two passes, and I fold it only after that review's REPLY. Never write "no review round needed". See [[design-prose-language-review]].

*References: design-prose-language-review*

*Observed 2026-10-16 (fabric-coordinator)*

---
role: "language-culture"
class: workflow
topic: "first-pass-settled-terms"
description: "The Georgian first pass flags established fabric terms; a re-render does not change them"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8167410bda91a2fb
---

## The Georgian first pass flags established fabric terms; a re-render does not change them

The Georgian first pass by `locale-worker`, which reads only the Georgian text and never the source, flags the established terms of the Georgian charter and team.md as foreign: "შეიარაღება" (arm), "ზედაპირი" (surface), "მაუწყებლობა" (broadcast), "მფლობელი" (used for both the human owner and the owning role), and the switching between PR and pull request. A re-render goes rule for rule (j55, team.md #253, commit e5d6b852), so those findings are recorded and declined. Changing a term means a glossary pass over the whole locale, not an edit to one paragraph.

**Why:** Changing a word in one file leaves the Georgian locale inconsistent. Terminology noise would also bury the worker's real findings, such as a missing object or "რვავე" read as "all eight".

**How to apply:** Split the first-pass findings in two. Accept the language findings inside the changed text. Record the findings about established terms as a glossary question, to be handled as a separate job.

*Observed 2026-10-14 (language-culture)*

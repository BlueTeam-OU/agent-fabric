---
role: "language-culture"
class: workflow
topic: "first-pass-fix-needs-source"
description: "A first-pass finding from the worker is often right while its proposed fix, made without the source, changes the meaning"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d13fbd4c3084cb9c
---

## A first-pass finding from the worker is often right while its proposed fix, made without the source, changes the meaning

On j73 (2026-10-16, commit 3270ba5c) the worker rightly flagged two unclear phrases, but its fixes changed the source meaning. Accept the first-pass finding; rewrite the fix from the source in the second pass, and record both.

*References: first-pass-settled-terms*

*Observed 2026-10-16 (language-culture)*

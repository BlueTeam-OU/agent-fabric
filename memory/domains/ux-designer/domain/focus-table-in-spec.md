---
role: "ux-designer"
class: domain
topic: "focus-table-in-spec"
description: When a spec names focus targets, list every case once in a single focus table in the acceptance section, each with its check, instead of scattering focus rules across sections
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 5a777cc6f2b6aede
---

## When a spec names focus targets, list every case once in a single focus table in the acceptance section, each with its check, instead of scattering focus rules across sections

Write focus as one table in the acceptance section: case, where focus
goes, how it is checked. The checks are keyboard (adb keyevent plus
uiautomator `focused="true"`), TalkBack (a person), or tests. Mark the
cases that cannot occur, such as a swipe with TalkBack on. Prose
sections then point to the table.

**Why:** in the InterWeave message-swipe spec (#286, 2026-10-16) three
review rounds in a row found focus targets with no acceptance check,
because each fix added a case in one section and its check elsewhere.
Round 4 asked for every case closed in one pass, and the table did it
(design/2026-10-16-message-swipe.md §11 item 21).

**How to apply:** whenever a spec says where focus goes, add or extend
the table row in the same edit. A focus target that is plain text,
such as a heading, must be made focusable in the spec too, or the
check can never pass.

Related: [[swipe-actions-j1]], [[undo-by-reverse-not-deferral]]

*References: swipe-actions-j1, undo-by-reverse-not-deferral*

*Observed 2026-10-16 (ux-designer)*

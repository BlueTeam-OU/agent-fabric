---
role: "rust-ui-dev"
class: domain
topic: "stack-actions-not-by-width"
description: Two or three action buttons whose labels carry meaning go one per line, full width, at every width and scale; switching layout by width fails first in a longer locale
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c630d91eae968278
---

## Two or three action buttons whose labels carry meaning go one per line, full width, at every width and scale; switching layout by width fails first in a longer locale

When an action's label is what tells the person what it will do ("Accept as a new contact",
"Close without saving"), squeezing two such buttons onto one row breaks the label mid-word at
200 % text scale, and a translated label may not fit one line even at 100 %. A layout that
switches to stacked "when narrow" chooses by width, but the failure comes from label length
and locale, which width does not know. The ruling in InterWeave (contact-cards 5.4 proposal,
then 5.2's unsaved-changes dialog, 2026-10-25): each action on its own line, full width of the
content column, at every width and scale; the reading/focus order the single row had (the
dismissive action first, the primary filled one last); a long label wraps inside its button,
which grows and never drops under the touch-target minimum (48 dp).

**How to apply:** for a dialog or card whose actions carry sentences, stack by default rather
than adding a width breakpoint; keep focus order equal to visual order; test at 200 % scale
with the longest locale or a pseudo-locale, rendered, not in the model alone.

*Observed 2026-10-31 (rust-ui-dev)*

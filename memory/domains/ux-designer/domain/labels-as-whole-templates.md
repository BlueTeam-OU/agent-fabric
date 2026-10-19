---
role: "ux-designer"
class: domain
topic: "labels-as-whole-templates"
description: Propose visible and spoken text as one whole template per case, never a prefix, a joined string or a template with optional parts, so a translation can reorder it
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ba36e007e2bcc103
---

## Propose visible and spoken text as one whole template per case, never a prefix, a joined string or a template with optional parts, so a translation can reorder it

When a design proposes text, it proposes it in the shape a translation
needs: a whole template with placeholders, one per case. A "You: "
prefix becomes "You: {message}"; a row description with and without an
unread count is two templates, not one with an optional part; AM and PM
are two time templates, not one with an {am_pm} word, because some
languages put that word before the time. The words stay
language-culture's; the shape is a layout input, so the designer gets it
right before handing over.

**Why:** on InterWeave's Android look (#293 and its follow-ups,
2026-10-16/17) language-culture-en reshaped three of my proposals this
way, each because the labels module fills placeholders and never joins
strings.

**How to apply:** for every new label, list its cases (present/absent
parts, singular/plural, 12/24-hour) and propose one template per case,
with what fills each placeholder.

Related: [[screen-reader-text-matches-what-is-shown]], [[wording-pass-keeps-conditions]]

*References: screen-reader-text-matches-what-is-shown, wording-pass-keeps-conditions*

*Observed 2026-10-18 (ux-designer)*

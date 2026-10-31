---
role: "ux-designer"
class: domain
topic: "screen-reader-text-matches-what-is-shown"
description: "Compose a screen-reader description against the element's label and the screen: never repeat what the label says, speak what a symbol only shows, and say what the sighted person sees"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0a6b8aefe07affd
---

## Compose a screen-reader description against the element's label and the screen: never repeat what the label says, speak what a symbol only shows, and say what the sighted person sees

A description is read after the element's accessible label, so:
- leave out what the label already says (a row labelled with its name
  read the name twice when the description held {name});
- put into words what is only drawn (a "#" before a channel name, read
  aloud, does not say "channel"; the kind must be spoken);
- speak what the sighted person sees, in the same place: a message
  bubble showing 13:05 under a "Yesterday" separator speaks "13:05", and
  the separator is its own item, reached before the run it heads, so
  the day is heard once per run;
- use one reading order on every platform the label reaches.

**Why:** InterWeave's Android look (#293, #295, 2026-10-16/17): a blind
review found the doubled name and the unspoken kind; rust-ui-dev-01's
build raised the bubble's reading order and its spoken time.

**How to apply:** for each description, write the label beside it and
read the pair aloud as the screen reader would; then compare with what
the screen shows at that spot.

Related: [[labels-as-whole-templates]], [[focus-table-in-spec]]

*References: focus-table-in-spec, labels-as-whole-templates*

*Observed 2026-10-18 (ux-designer)*

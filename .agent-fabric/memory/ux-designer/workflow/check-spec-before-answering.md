---
role: "ux-designer"
class: workflow
topic: "check-spec-before-answering"
description: "Before choosing among a developer's options, search the specs' existing tables and the tree: the answer is often already written (the build deviates) or the case does not exist in the product"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f5a293e031897843
---

## Before choosing among a developer's options, search the specs' existing tables and the tree: the answer is often already written (the build deviates) or the case does not exist in the product

A developer's "which do you want, (a) or (b)?" is framed from the code.
Three of five such questions in two days were not open:
- two were already specified elsewhere (a key's name in another note's
  strings table; the Contacts title as a focusable heading in
  contact-cards' focus table, which the build had not followed): the
  answer was "the build deviates from row N", not a new rule;
- one rested on a case the product does not have (two open
  conversations; the view holds one), from an unchecked plan.
Answering the options as asked would have written a second rule beside
the first, or specified a case that cannot occur.
**Why:** InterWeave start window B2 and B3, 2026-10-28/30.
**How to apply:** before answering, grep every design note for the keys,
controls and states named, and check the case in the tree; answer with
the existing line quoted and call the build's difference a deviation
for the developer to fix, and ask where a case comes from before
specifying it.
Related: [[restated-conditions-quoted-verbatim]], [[finding-says-what-has-to-change]]

*References: finding-says-what-has-to-change, restated-conditions-quoted-verbatim*

*Anchors: `interweave:design/2026-10-21-contact-cards.md::the page title (focusable heading)`*

*Observed 2026-10-31 (ux-designer)*

---
role: "brand-comms"
class: domain
topic: "marp-overflow-eats-margins"
description: "A Marp slide that is too tall does not clip — vertical centring spends its margins first, so \"it fits\" by eye can be an overflow; measure section scrollHeight, per language"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: gzapp.decks
    working_copy: gzapp.decks
derived_from:
  - 5b867442edfb0953
---

## A Marp slide that is too tall does not clip — vertical centring spends its margins first, so "it fits" by eye can be an overflow; measure section scrollHeight, per language

Marp centres a slide's content vertically. A slide whose content is taller
than the frame does not visibly clip: the title rises toward the top edge
and the last line runs down into the credit or footer. By eye that reads
as "fits, a bit tight".

Measured on gita-pitch v2.4.1 (2026-10-30, the deck-review trial, PR
gzapi-org/gzapp.decks#33): in the Georgian deck, pages 5 and 9 have
`section.scrollHeight > clientHeight`. On page 5 the title sits about 90px
from the top, against 200px in English, and the privacy line is about
20px above the photo credit. The v2.4.0 commit f54a9bf had called page 5
fitting.

**How to apply:** after any change that lengthens copy, and always for
Georgian, compare each slide's title height from the top across languages,
or measure overflow on Marp's HTML output (the `deck-review` skill's
assessment B). Never call a translated slide fitting from the render alone.
Related: [[deck-review-ledger-before-blind-findings]].

*References: deck-review-ledger-before-blind-findings*

*Observed 2026-10-30 (brand-comms)*

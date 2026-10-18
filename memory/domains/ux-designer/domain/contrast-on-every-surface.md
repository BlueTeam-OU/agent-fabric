---
role: "ux-designer"
class: domain
topic: "contrast-on-every-surface"
description: "Measure a mark's contrast against every surface it can sit on (snackbar, notice, bubble, selection), not only the screen background"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 01494f6bf204e458
---

## Measure a mark's contrast against every surface it can sit on (snackbar, notice, bubble, selection), not only the screen background

When a spec gives a colour to a mark that appears on several containers
(a focus ring, a swipe's neutral fill, an unread dot), list one contrast
row per container it can sit on, in both schemes.

**Why:** the InterWeave Android look (design/2026-10-16-android-look.md,
#293, 2026-10-16/17) checked the focus ring and the neutral swipe fill
only on `surface`. The review found the ring at 1.34:1 on the snackbar and
the fill at 1.97:1 on a sent bubble, and the light unread dot at 1.36:1.

**How to apply:** for each coloured mark, enumerate where it is drawn
(including inverse surfaces and fixed-colour banners), compute each pair
(WCAG 2.2, 3:1 for non-text, 4.5:1 for text), and give a per-container
role where one value cannot pass everywhere.

Related: [[focus-table-in-spec]]

*References: focus-table-in-spec*

*Observed 2026-10-17 (ux-designer)*

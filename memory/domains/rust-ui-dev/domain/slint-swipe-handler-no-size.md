---
role: "rust-ui-dev"
class: domain
topic: "slint-swipe-handler-no-size"
description: "Slint 1.18 - a component whose children are all `if` gets no size; bind min/preferred-height to an inner layout, and test geometry at 390 px"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - f33317d479963693
---

## Slint 1.18 - a component whose children are all `if` gets no size; bind min/preferred-height to an inner layout, and test geometry at 390 px

Slint 1.18: a component (e.g. `inherits Rectangle`) whose only children are `if cond: Layout {}` blocks
passes no layout size up, so it is drawn 0 px tall and its content spills (clip: true then hides it
from `find_by_accessible_label` too). Wrapping them in one unconditional layout gives it a size, but
under the real software renderer the height was still measured before word-wrap at the actual width
(actions drawn below the card at 390 px) - bind `min-height`/`preferred-height` to the body layout
explicitly. A too-wide child (a non-wrapping HorizontalLayout of buttons) makes the whole Flickable
scroll sideways, which then eats a leftward drag before any SwipeGestureHandler sees it.
How to apply: geometry tests at phone width (390x800) asserting the last control lies inside the
card, and a rendered snapshot (`take_snapshot` under tools/ci/with_display.sh, desktop feature).
InterWeave: ProposalCard, commits 5182af6f, 8a92a849, e7538614 (j54 batch 3). See [[slint-layout-traps-seen-rendered]].

*References: slint-layout-traps-seen-rendered*

*Observed 2026-10-25 (rust-ui-dev)*

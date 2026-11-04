---
role: "rust-ui-dev"
class: domain
topic: "slint-layout-traps-seen-rendered"
description: Slint 1.18 layout traps the testing backend hid and only a rendered window showed — wrapped TextInput height, window first height, invisible elements keeping space
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 88a92e8e5c263d3c
---

## Slint 1.18 layout traps the testing backend hid and only a rendered window showed — wrapped TextInput height, window first height, invisible elements keeping space

Found on 2026-10-20 while building the desktop start-up refusal screen (InterWeave #327,
`crates/human/ui-slint/ui/app.slint` `RefusalWindow`). Every view test passed; a screenshot
under Xvfb (`tools/ci/with_display.sh` + ImageMagick `import -window root`) showed three
defects:

1. **A read-only `TextInput` with `wrap: char-wrap` does not grow its box to its wrapped
   lines**: `height: field.preferred-height` gives about one line, so a long path overran
   and pushed the content past the window. Fix: put a transparent `Text` (same text, font
   and wrap, `accessible-role: none`) in a `VerticalLayout` inside the box. The box then
   takes its height-for-width from the layout, and the field overlays it with
   `width/height: parent`.
2. **A `Window` sizes itself before its wrapped lines are measured at its width**, so it can
   open shorter than its content and clip whatever sits at the bottom. Fix: state
   `preferred-height`, put the text in a `Flickable` (`content-height:
   body.preferred-height`; `viewport-height` is deprecated and fails the
   warnings-as-errors compile test) and keep the actions outside it, so they stay in view.
3. **`visible: false` keeps the element's layout space.** It is out of the focus chain and
   the accessibility tree, both measured, but a hidden button still pushed its neighbour
   off the row's edge. Use `if cond: Element`, and focus it through a sequence property
   (`focus-seq` / `focus-wanted` on `ActionButton`), since an id inside `if` cannot be named.

Also: a scope that only catches Escape needs `focus-on-tab-navigation: false`. Otherwise
Tab stops on it and does nothing. The Tab-order test caught that one.

**How to apply:** look at a rendered window before calling a Slint screen done, and turn
each defect seen there into a geometry test on the testing backend. Its text metrics differ
from the real ones, but item 2 reproduced there once the test asserted the actions'
bottom against the window's own height.

*Observed 2026-10-20 (rust-ui-dev)*

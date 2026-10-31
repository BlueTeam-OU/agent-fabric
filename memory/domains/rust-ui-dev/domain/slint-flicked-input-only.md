---
role: "rust-ui-dev"
class: domain
topic: "slint-flicked-input-only"
description: "Slint 1.18 Flickable's flicked fires only on wheel, drag and fling; focus reveal and programmatic content-y moves don't fire it, so track scroll position with changed content-y"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - d56c38762a3ca9e4
---

## Slint 1.18 Flickable's flicked fires only on wheel, drag and fling; focus reveal and programmatic content-y moves don't fire it, so track scroll position with changed content-y

In i-slint-core 1.18.1 `items/flickable.rs`, `flicked` is invoked only from pointer input: wheel, drag and fling start (lines ~563, 587, 669, 903). `reveal_points`, the scroll that brings a focused item into view, sets content_y directly, and so does any assignment from .slint. Neither fires `flicked`.

InterWeave #313's F9 pin keyed on `flicked`. Tabbing into a conversation's history left the list "pinned", and the next arrival jumped it to the end (round 6 finding 1). The fix, 6f8162e3, uses `changed content-y` to recompute "at end". A clamp after a resize lands at the end, so it keeps the pin.

Also: a Flickable shared by several conversations keeps its offset across a switch. Re-pin on the shown key's change.

Host tests need the change handlers run: call update_timers_and_animations, then mock_elapsed_time, then update again after each step. Without that, a views test sees the state before the handlers ran.

*Observed 2026-10-20 (rust-ui-dev)*

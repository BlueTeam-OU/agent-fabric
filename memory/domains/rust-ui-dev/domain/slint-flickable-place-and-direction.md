---
role: "rust-ui-dev"
class: domain
topic: "slint-flickable-place-and-direction"
description: "Slint 1.18 Flickable - keeping a row's place when rows are inserted above, and telling the person's scroll from the app's"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 469f7c0365c27d45
---

## Slint 1.18 Flickable - keeping a row's place when rows are inserted above, and telling the person's scroll from the app's

Seen building InterWeave #512 (crates/human/ui-slint/ui/app.slint, window_marks.rs), 2026-10-30.

Keeping a row's on-screen place as rows are inserted above it:
- Rows inserted in a repeater are laid out over MORE than one change: the anchor row's `y` first moves with stale
  zero-height new rows, then again once they are laid out. A content-height-delta compensation consumed on the
  first `changed content` loses the second.
- The Flickable clamps a positive `content-y` back to 0, so summing per-change deltas drifts by the clamped part.
- What worked: an absolute target. Rust names the anchor row (focused, else first in view) and arms a follow for
  the render that inserts rows above it (render-seq/follow-seq properties); the row records its on-screen place
  on the first change of the burst and sets `content-y = target - item-top` on every change until the next render.
- Follow the message's bubble (`row.y + row-content.y + item.y`), not the row: a day separator handed to the new
  rows moves the bubble inside its row (17 px off otherwise).
- The testing backend draws nothing, so layout of new rows only happens when something reads geometry: a test must
  force layout per frame (read every element's absolute_position between update_timers_and_animations calls). In a
  real window the follow lands a frame late.

Telling the person's scroll from the app's:
- `changed content-y` fires for the app's own moves and the toolkit's clamps too. `flicked` is called only from the
  person's wheel/drag/fling input, synchronously after the offset moved and BEFORE deferred change handlers run, so
  a `last-y` updated in `changed content-y` still holds the old offset inside `flicked`.
- The toolkit's scroll bringing a focused element into view fires no `flicked`: take focus direction separately
  (order of the old and new focused element in reading order).
Related: [[slint-layout-traps-seen-rendered]], [[slint-focus-request-needs-focus-wanted]].

*References: slint-focus-request-needs-focus-wanted, slint-layout-traps-seen-rendered*

*Observed 2026-10-30 (rust-ui-dev)*

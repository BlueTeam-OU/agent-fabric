---
role: "rust-ui-dev"
class: domain
topic: "slint-swipe-in-flickable"
description: "Slint 1.18.1 swipe rows inside a Flickable: what the toolkit does to a press, how to move a row without breaking its height, what a device showed (j82, #289)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - a0232c6071df69c2
---

## Slint 1.18.1 swipe rows inside a Flickable: what the toolkit does to a press, how to move a row without breaking its height, what a device showed (j82, #289)

Learned building row swipes in crates/human/ui-slint (InterWeave#289, merged 925bd6e9, 2026-10-16), measured on the Pixel 9a:
- A press inside a scrollable Flickable reaches its children ~100 ms late (flickable.rs FORWARD_DELAY, DelayForwarding), and SwipeGestureHandler delays it again in its own filter (input_items.rs:898). Moves before that never reach the row: a 60-100 ms flick gives no `moved`, a 150 ms one a single sample. A fling rule needing samples in the last 100 ms cannot work there.
- SwipeGestureHandler is the one element that takes a drag from child buttons; its own threshold (dx > |dy|/2) is looser than a slop-plus-larger-axis rule, so decide the drag in Rust from its pressed/current positions. The parent Flickable still intercepts on |dy| > 8 within 500 ms; set the list `interactive: false` once the row tracks.
- A child with an `x` (or `y`) binding is EXCLUDED from its parent's layout info (default_geometry.rs gen_layout_info_prop), so an `x`-moved content loses wrapped height. Move it with a HorizontalLayout `padding-left: off; padding-right: -off` instead (padding is plain arithmetic, negative allowed).
- `clip` only on Rectangle/Path; Path needs `slint/software-renderer-path` on the desktop software renderer (its crates were already in the lock).
- Collapsing a row: hold `max-height` at the height captured by `changed height`, then a Timer flips to 0 with an animation.
- TouchArea's `clicked` fires after ANY drag released inside the area. On a phone, a drag over a row that offers no swipe read that conversation's unread messages unseen (data loss, j88 item 17). Build every tap control on a TouchArea that fires only while the finger stays within the platform slop, during the press and at release (app.slint `TapArea`, slop from the Android ViewConfiguration).
- SwipeGestureHandler grabs a press on non-control content and reports every move, but sends NO callback when a touch it never swiped ends, so a Rust gesture state goes stale and the next drag is dead (item 5). Wrap the row's content in a TouchArea, so the handler reports only drags it has taken.
- Host pointer tests through the testing backend must hold the press ~120 ms before moving, or the Flickable's forwarding delay eats the moves, as on the device.
- The fling is therefore a time window from the first move the row sees (released within 100 ms of it, >= 48 moved from touch-down), the swipe spec's rule (ux-designer ruling 01a1464b); a flick under ~100 ms springs back.
- `adb shell input motionevent DOWN/MOVE/UP` holds a swipe for a screenshot; `input swipe` is fast and hits the delays above.
Related: [[slint-rendered-window-lessons]]

*References: slint-rendered-window-lessons*

*Observed 2026-10-18 (rust-ui-dev)*

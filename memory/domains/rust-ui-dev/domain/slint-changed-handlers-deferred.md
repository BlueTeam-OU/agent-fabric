---
role: "rust-ui-dev"
class: domain
topic: "slint-changed-handlers-deferred"
description: "Slint `changed prop =>` handlers run at the event loop's next turn, not on the change; never keep a Rust copy of a window-derived state, read it live"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - f872a7cb6e73abc1
---

## Slint `changed prop =>` handlers run at the event loop's next turn, not on the change; never keep a Rust copy of a window-derived state, read it live

In Slint 1.18 a `changed <prop> => {}` handler does not run when the property changes: `ChangeTracker::run_change_handlers` is called from the event loop's `update_timers_and_animations` and before a draw (i-slint-core `context.rs`, `window.rs`). In tests on `i_slint_backend_testing::init_no_event_loop()` they run only on `slint::platform::update_timers_and_animations()` (or `mock_elapsed_time`).

So a Rust-side copy of something the window derives (which pane a narrow window shows) is stale between the change and that turn, and goes stale for good if one path that changes it (a resize) never reports. j84 (BlueTeam-OU/InterWeave#291, 15c3effd): `Page::List` kept beside `list-shown` let a resize show the list while a conversation was still read. Fix shape: an `out property` (`pane-shown`) the view reads AT THE MOMENT OF DECIDING, plus one `changed` handler only to wake the root for side effects (snackbar close, read on return), resolved after the queue drains.

Also learned (three review rounds on #291): a no-payload signal the WINDOW raises (pane shown/hidden) can wait outside the input queue as a flag resolved after the drain; a PERSON'S PRESS (Back) cannot. As a flag it has no position, so whichever take resolves it is wrong for a press on one side of it (round 2: drain-take closed a snackbar made after return; round 3: first-take missed one a Dismiss before Back made). Keep presses queued; a press that depends on an earlier press's not-yet-applied intent re-queues itself at the front and ends the take. And removing an earlier queue entry to keep the last makes neighbouring focus changes adjacent, breaking the bound. Related: [[slint-rendered-window-lessons]], [[model-only-take-rerender]].

*References: model-only-take-rerender, slint-rendered-window-lessons*

*Observed 2026-10-16 (rust-ui-dev)*

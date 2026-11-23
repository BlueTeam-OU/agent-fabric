---
role: "rust-ui-dev"
class: domain
topic: "slint-android-input-batch-stale-page"
description: Slint 1.18.1 Android dispatches every queued input before timers run, so a view rule judged on a page rebuilt by a deferred callback sees a stale page
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 586ddff80e7a913e
---

## Slint 1.18.1 Android dispatches every queued input before timers run, so a view rule judged on a page rebuilt by a deferred callback sees a stale page

i-slint-backend-android-activity 1.18.1 `process_inputs` loops `input_events_iter` until it is empty, and dispatches each key with no timer turn between them. Timers (`update_timers_and_animations`) run once per `poll_events` callback. InterWeave applies identity inputs through `ui_slint::defer` (a zero-duration `slint::Timer::single_shot`), so keys that arrive together are all dispatched against the page shown before the first of them was applied.

Consequence: a `.slint` rule that reads `page.*` to decide what a key does (R2's Enter rule `enter-takes()`) is wrong under a burst. j261 fixed it by sending Enter to the flow (`IdentityInput::Enter` → `IdentityFlow::enter` → `WordPicker::enter_chip`), which judges in order. The rule is: a decision that depends on model state goes to the model as an input, never to the view's copy of the page.

Host reproduction: dispatch the KeyPressed/KeyReleased events back to back, then apply the queue (trace.rs `Identity::burst`). PR #634.
Related: [[j261-r2-enter-art]] [[model-only-take-rerender]] [[key-driven-ui-settled-focus]]

*References: j261-r2-enter-art, key-driven-ui-settled-focus, model-only-take-rerender*

*Observed 2026-11-12 (rust-ui-dev)*

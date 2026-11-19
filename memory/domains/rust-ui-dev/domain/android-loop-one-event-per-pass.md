---
role: "rust-ui-dev"
class: domain
topic: "android-loop-one-event-per-pass"
description: "Slint android loop takes one looper event per pass and runs due timers first; a repeated timer re-arms at fire time, so long timer work starves input; keys pass twice (IME pre-dispatch)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 270f084726d9fe7d
---

## Slint android loop takes one looper event per pass and runs due timers first; a repeated timer re-arms at fire time, so long timer work starves input; keys pass twice (IME pre-dispatch)

Measured on the A40 (j107, 2026-11-13) with i-slint-backend-android-activity 1.18.1 and android-activity 0.6.1 (native-activity):

- Each loop pass is one `ALooper_pollOnce`; its callback runs `update_timers_and_animations()` BEFORE the event is processed. So every input event, and every `invoke_from_event_loop` task, waits behind whatever timer work is due.
- A `TimerMode::Repeated` timer re-arms at `now + interval` when it fires (before its callback runs). A callback longer than the interval leaves the timer due again as it ends, so the next pass runs it again. Changing the interval (1 ms or 16 ms) changes nothing.
- A key passes through the loop twice (AInputQueue pre-dispatch to the IME, then the dispatch). InputDispatcher sends one key at a time. So a Back is press x2, release x2, then the Activity's onBackPressed, then the invoke back to the loop: about six passes.
- `adb shell input keyevent` sends the release only after the press is finished. On a busy phone the release can come more than 40 ms after the press reached the Activity.
- The fix pattern (ui-slint `open_reader`, commits 4257d77f3 and c3f15adf5): after each turn, skip one pass without work. Hold the work for 150 ms after the event listener sees `MainEvent::InputAvailable`.
- To log a key's true press time: in the Activity's `dispatchKeyEvent`, log `uptimeMillis() - event.eventTime`. Only keys the native side leaves unhandled reach it.

Related: [[j107-handoff]], [[j95-a40-ab-rig]].

*References: j107-handoff, j95-a40-ab-rig*

*Observed 2026-11-13 (rust-ui-dev)*

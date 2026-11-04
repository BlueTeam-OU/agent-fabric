---
role: "rust-ui-dev"
class: domain
topic: "slint-android-host-driving"
description: "Driving a Slint Android app's screens from the host in e2e tests, with no accessibility tree -- keyevents move focus, FLAG_SECURE blanks screencap, a debug-only logcat trace gives the done signal"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 39efbdb6c9cf98e0
---

## Driving a Slint Android app's screens from the host in e2e tests, with no accessibility tree -- keyevents move focus, FLAG_SECURE blanks screencap, a debug-only logcat trace gives the done signal

Slint on Android draws no accessibility tree, so neither UiAutomator nor the host can find a
control by its label. What was measured on a Samsung A40 (API 30) and a Pixel 9a, 2026-10-25:
- `adb shell input keyevent` TAB, ENTER and ESCAPE drive Slint's own focus: the ring draws,
  ENTER activates, and ESCAPE closes a menu with focus back on its button. Screens can be
  driven by key, in each screen's fixed tab order.
- Focus survives `am start`, because the running activity is reused. Start each step from a
  known state: force-stop, then launch. On a fresh launch the first TAB once drew no ring.
- A FLAG_SECURE screen screencaps black. The capture proves only that a secure screen is up,
  never what it shows. Take the shown value from the core (own addresses), not from pixels.
- An instrumentation that runs the Rust service in its own process never starts the Activity,
  so a UI case cannot run inside it. Drive the real app from the host instead.
- A counted TAB that lands on the wrong control presses the wrong button unseen. Give the host
  a signal it can wait on: a trace in the debug build only, under one logcat tag, that logs
  the page, the focused control's focus key and each step's outcome kind, and never
  person-facing text, an address, an id or a name. Gate it twice: a release-artifact scan that
  fails when the trace marker is present (break the gate once to prove it), and a test that
  feeds the trace a page holding addresses and names and fails on a leak (mutate it once).
- Two driver faults: judge focus only once it settles, and make each wait read every line
  from its key press onward.
State: the trace is on the scan-path-ui for/ branch, not on InterWeave main as of 2026-10-27.
Related: [[device-tests-host-first]], [[device-case-reads-while-connected]].

*References: device-case-reads-while-connected, device-tests-host-first*

*Observed 2026-10-27 (rust-ui-dev)*

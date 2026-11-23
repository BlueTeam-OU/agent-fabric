---
role: "rust-ui-dev"
class: domain
topic: "key-driven-ui-settled-focus"
description: "driving a Slint Android app by adb keyevents through a focus trace -- judge settled focus, scan waits from the press, menus emit no render"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - b42893153b3fd5b1
---

## driving a Slint Android app by adb keyevents through a focus trace -- judge settled focus, scan waits from the press, menus emit no render

Driving the InterWeave Android app by `adb shell input keyevent` and reading where focus went from a logcat trace (j158, 2026-10-25, Pixel 9a + A40):
- A page moves focus on its own when it opens (Peers to its title). Taking the first focus line after a TAB as that TAB's answer pressed ENTER one control late (Add opened instead of Show). Judge the SETTLED focus: read until the trace is quiet (~700 ms) before and after each TAB.
- One render writes several lines (page before outcome). A wait that consumes lines swallows the one the next wait needs: record the line index at the key press and scan everything from there, wanting a set in any order.
- State Slint changes without a Rust render (the app menu opening) never reaches a render-sampled trace; use a focus change (the menu's first entry taking focus) as the sign.
- Focus survives `am start` of a running activity: force-stop before a step that must start from a known focus.
- A release-only check by marker string (verifyReleaseNative scanning the .so for "ui-trace") is proved by forcing the feature into the release build once: it failed, then passed as committed.
**Why:** each of these made a driver step report the wrong control or hang on the first device run.
**How to apply:** any host-side driver of a Slint app by key events; see tests/android-e2e/src/screen.rs on the for/p2p-network-dev-02/scan-path-ui branch.

*Observed 2026-10-25 (rust-ui-dev)*

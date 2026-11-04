---
role: "ux-designer"
class: workflow
topic: "scripted-input-on-shared-phone"
description: "Scripted adb input on the shared test phone: check before every tap that the app holds focus, wait out system heads-ups, stop when a person uses the phone, read FLAG_SECURE before trusting a black capture, and log every anomaly with build…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b67633336a3b5e3d
---

## Scripted adb input on the shared test phone: check before every tap that the app holds focus, wait out system heads-ups, stop when a person uses the phone, read FLAG_SECURE before trusting a black capture, and log every anomaly with build and time

Blind coordinates hit whatever is in front. One scripted Back left the
app (a defect under review) and the next tap switched Wireless
debugging off; another lost a test row. After each `adb connect` a
"Wireless debugging connected" heads-up offers "tap to turn off" over
the top of the screen.
- Before every input: read the focused window (dumpsys window) and stop
  unless it is the app under review; wait for heads-ups to clear.
- When another app comes to the front during a run, a person is using
  the phone: stop all input and say so.
- A black capture may be the app's FLAG_SECURE (read the window flags),
  not a dead screen; then hold and ask, since secret words may be open.
- Record every anomaly with build, phone time and screen, even one put
  down to slowness: such a note bisected a defect to one commit the
  next day.
- Restore and read back every setting changed (rotation, font scale,
  theme, locale) before release.
**Why:** InterWeave Pixel 9a runs, 2026-10-19 to 10-21.
Related: the project slice "How ux-designer reaches InterWeave's Android
test phone" (lease, pairing, build proof), which this extends.

*Observed 2026-10-22 (ux-designer)*

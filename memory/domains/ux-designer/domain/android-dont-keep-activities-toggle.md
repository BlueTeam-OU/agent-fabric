---
role: "ux-designer"
class: domain
topic: "android-dont-keep-activities-toggle"
description: "On the Pixel (GrapheneOS), `settings put global always_finish_activities` does not apply Don't keep activities; only the Developer options switch does"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 24b84d968e822ad1
---

## On the Pixel (GrapheneOS), `settings put global always_finish_activities` does not apply Don't keep activities; only the Developer options switch does

2026-11-15, j129 Pixel run: `adb shell settings put global always_finish_activities 1` changed the value but Home kept the window
(`am start`: "Activity not started, its current task has been brought to the front"; same window id). After the owner switched
the option off and on in Developer options, Home ended the window (a second `android_main: the Activity's views start`).
`cmd activity` has no command for it. Setting it back is the same: the switch, by a person at the phone.

**How to apply:** a device run that needs the option asks the person to switch it at the start AND to switch it back at the end,
inside the slot; plan the slot around both asks, and verify with the window-made-again log line, never the setting value.
Related: [[workflow-carried-2026-10-18]], [[j124-launch-count-658]].

*References: j124-launch-count-658, workflow-carried-2026-10-18*

*Observed 2026-11-15 (ux-designer)*

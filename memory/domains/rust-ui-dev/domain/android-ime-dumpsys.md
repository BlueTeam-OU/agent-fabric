---
role: "rust-ui-dev"
class: domain
topic: "android-ime-dumpsys"
description: "Driving an Android app by adb keyevents — BACK is eaten by the soft keyboard while a text field is focused; read mInputShown as a token (API 30 prints it mid-line)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 453399f872e9e2e5
---

## Driving an Android app by adb keyevents — BACK is eaten by the soft keyboard while a text field is focused; read mInputShown as a token (API 30 prints it mid-line)

With a text field focused the soft keyboard is up and the platform spends a KEYCODE_BACK on hiding it; the app never sees that Back. A driver checks `dumpsys input_method` for `mInputShown=true` first, Backs once and waits for false. API 36 (Pixel 9a) prints `mInputShown=` alone on a line; API 30 (Samsung A40) prints it after `mShowRequested=… mShowForced=…` on one line, so read it as a whitespace token, never by line prefix. Shown in InterWeave tests/android-e2e/src/screen.rs (`keyboard_shown`, 21dd5917/e3234d2b), measured 2026-10-30.

*Observed 2026-10-30 (rust-ui-dev)*

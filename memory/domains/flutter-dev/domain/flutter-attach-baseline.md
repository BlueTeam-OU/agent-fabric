---
role: "flutter-dev"
class: domain
topic: "flutter-attach-baseline"
description: "flutter attach takes the CURRENT source as what the device runs: edits made before attaching never hot-reload; attach first, then edit"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - dd9551e6557805cd
---

## flutter attach takes the CURRENT source as what the device runs: edits made before attaching never hot-reload; attach first, then edit

`flutter attach` to an installed debug APK compiles the current tree as its baseline, so an edit made
BEFORE attaching reloads "0 libraries" and even a hot restart (SIGUSR2) did not apply it (2026-10-10,
measured: identical pixel bands before/after). Working order: put the source back to what the APK was
built from, attach (`ANDROID_ADB_SERVER_PORT=<make ports adb> flutter attach -d <serial> --pid-file f`),
THEN apply the edit and `kill -USR1 $(cat f)` — "Reloaded 1 of N libraries". Detach by killing the pid.
**Why:** each APK rebuild waits on the shared heavy lease (10-60 min on a busy host).
**How to apply:** for visual iteration on the phone, attach once, edit after.

*Observed 2026-10-10 (flutter-dev)*

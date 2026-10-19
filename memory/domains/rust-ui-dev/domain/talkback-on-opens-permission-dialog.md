---
role: "rust-ui-dev"
class: domain
topic: "talkback-on-opens-permission-dialog"
description: "Turning TalkBack on over adb on the Pixel 9a opens a phone-call permission dialog that takes every injected key; check the focused window before each step"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2f4ecb7949768c4b
---

## Turning TalkBack on over adb on the Pixel 9a opens a phone-call permission dialog that takes every injected key; check the focused window before each step

j104, 2026-10-18, Pixel 9a. Turning TalkBack on over adb (`settings put secure
enabled_accessibility_services com.android.talkback/com.google.android.marvin.talkback.TalkBackService`
plus accessibility_enabled 1) shows two things. First, TalkBack's TrainingActivity tutorial, which
Back dismisses. Then com.android.permissioncontroller's GrantPermissionsActivity: "Allow TalkBack to
make and manage phone calls?". That dialog took every injected `input keycombination`
(ALT_LEFT+DPAD_RIGHT, ALT_LEFT+ENTER). Each one still returned rc=0, so the whole of phase A.1
measured the dialog and not the app. The tell was in the evidence: the screenshots darkened behind
its shade (mean luma 39 -> 25), and the uiautomator dumps held no org.interweave.human node.

How to apply:
- After turning TalkBack on, answer or dismiss that dialog before driving anything.
- Before each injected step, assert `dumpsys window | grep mCurrentFocus` names the app under test.
- An rc=0 from `input` proves only that the event was delivered, never where it went.

Outcome: the owner's DECISION (architect-cto-01, 01a14e7d) carried Android TalkBack to the release
gate, so no rerun was needed.

*Observed 2026-10-18 (rust-ui-dev)*

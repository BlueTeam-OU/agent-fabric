---
role: "rust-ui-dev"
class: domain
topic: "android-settings-observe-live"
description: "Android settings a UI follows (accessibility timeouts, animator scale, 12/24-hour) change while the app is in front -- observe them, never read once at start or resume"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c684dc37030aa7c7
---

## Android settings a UI follows (accessibility timeouts, animator scale, 12/24-hour) change while the app is in front -- observe them, never read once at start or resume

A person can change a system setting the client follows while the client stays in front and
gets no resume: Settings beside it in split screen, a quick-settings tile, or `adb shell
settings put`. A value read once at start or in onResume stays stale. Measured on a Pixel 9a
(Android 17): a snackbar still closed after about 7.7 s with
accessibility_interactive_ui_timeout_ms set to 30000, because the app had read the default.

So, for every setting that drives a UI value (Secure accessibility_interactive_ui_timeout_ms
and accessibility_non_interactive_ui_timeout_ms, Global ANIMATOR_DURATION_SCALE, System
TIME_12_24 / DateFormat.is24HourFormat, and the like):
- register a ContentObserver on its URI while the window is shown, and push the new value to
  the core on change;
- read it again a short moment after the change too. AccessibilityManager's
  getRecommendedTimeoutMillis learns the new timeout on its own path, which can land after
  the observer fires. Send nothing when the value has not changed;
- test both cases on the device: changed with the app open, and changed before a restart.

**Why:** "honours the reduced-motion / longer-timeout / 24-hour setting" is a promise about
the person's current choice, and a stale read breaks it silently. A test that sets the value
before launch never sees the gap.
**How to apply:** when a client reads any platform preference, ask "what if it changes now?".
Wire the observer in the same change that adds the read. Related:
[[platform-copy-per-situation]], [[network-denied-posture]].

*References: network-denied-posture, platform-copy-per-situation*

*Observed 2026-10-18 (rust-ui-dev)*

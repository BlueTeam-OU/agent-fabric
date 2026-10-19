---
role: "flutter-dev"
class: domain
topic: "flutter-no-guarded-zone-two-handlers"
description: "A Flutter app's error sink is FlutterError.onError plus PlatformDispatcher.instance.onError — wrapping bootstrap in runZonedGuarded switches the second one off."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ec3a13f1d7e68ac7
---

## A Flutter app's error sink is FlutterError.onError plus PlatformDispatcher.instance.onError — wrapping bootstrap in runZonedGuarded switches the second one off.

To collect every error in a release build, install exactly two handlers:
`FlutterError.onError` (framework-raised errors and every
`FlutterError.reportError` call) and `PlatformDispatcher.instance.onError`
(what reaches the root isolate unhandled). Do **not** add a
`runZonedGuarded` around bootstrap as a "third net": async errors do not
cross between zones with different handlers, and `PlatformDispatcher.onError`
is reached only through the root isolate's unhandled-error hook, so the
guarded zone takes the second handler out of service for everything inside
it — a handler installed, mandated and unable to fire. `ErrorWidget.builder`
is neither: it only decides what a failed build paints.

**Why:** a project rule once mandated all three; the correction came before
anyone built it (the decision record now excludes the zone).
**How to apply:** when wiring or reviewing an error sink, look for
`runZonedGuarded` around `runApp` and remove it; check both handlers exist.

*Observed 2026-10-15 (flutter-dev)*

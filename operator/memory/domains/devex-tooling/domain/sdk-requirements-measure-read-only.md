---
role: "devex-tooling"
class: domain
topic: "sdk-requirements-measure-read-only"
description: "What an Android build needs from a shared SDK is measured against a READ-ONLY tree — a writable SDK lets Gradle install the gaps silently"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 07c8de0ca6ed76a8
---

## What an Android build needs from a shared SDK is measured against a READ-ONLY tree — a writable SDK lets Gradle install the gaps silently

A Gradle/AGP build against a writable Android SDK installs any missing
component itself and says nothing, so a "verified" list of what a
project needs, taken from a build on a writable copy, is short. On
2026-10-20 a writable-overlay build of gzapp's passenger APK reported
build-tools 35, platforms 34 and 37 as the gaps; the same build against
the staged tree made `chmod -R a-w` failed asking for platforms;android-35
(flutter_appauth, jni, flutter_foreground_task), and CMake 3.22.1
(Flutter's Gradle plugin forces an empty native build in every app) was
also missing. InterWeave #325 pins all five as HOST_PKG_<n>.

**Why:** the silent install is the stand-in problem
([[a-passing-run-without-the-trigger-measures-nothing]]): the writable
copy measured itself, not /opt/android-sdk, which is root's.

**How to apply:** to check a pin set, `--stage`, `chmod -R a-w` the
staged root, build with ANDROID_HOME and `flutter config --android-sdk`
pointing at it; the control is one run that fails asking for a component.
Enumerate plugins' `compileSdk` from the pub cache first (lockfile →
~/.pub-cache/hosted/pub.dev/<name>-<ver>/android/build.gradle*) to cut
the 12–17 min rebuild cycles. Restore `flutter config` afterwards and
remove the ~4 GB ~/.gradle the build creates. `--no-pub` after a manual
`pub get` keeps a registrant with dev dependencies (integration_test)
and fails the release compile — build without it.

*References: a-passing-run-without-the-trigger-measures-nothing*

*Observed 2026-10-20 (devex-tooling)*

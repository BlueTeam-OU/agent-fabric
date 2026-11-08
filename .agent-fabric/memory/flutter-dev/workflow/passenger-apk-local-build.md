---
role: "flutter-dev"
class: workflow
topic: "passenger-apk-local-build"
description: "How to build gzapp's passenger release APK on develop-qzapp despite the read-only, incomplete /opt/android-sdk; never run flutter test during the build"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 443c08970bc0d691
---

## How to build gzapp's passenger release APK on develop-qzapp despite the read-only, incomplete /opt/android-sdk; never run flutter test during the build

On develop-qzapp (2026-10-19) `flutter build apk --release --target-platform android-arm64` for apps/passenger_flutter fails on the host as provisioned:
- the default Java 25 is refused by Gradle 8.14;
- /opt/android-sdk (root-owned, not writable) lacks build-tools 35.0.0 and platforms 34 and 37;
- AGP wants the hash `android-37`, but the platform installs as `android-37.0`.

Recipe that built it (24.4 MB, about 17 min):
1. JDK 17: `flutter config --jdk-dir /opt/android-sdk/jdk` once per login (devex-tooling's chosen fix; no host-wide JAVA_HOME), or `JAVA_HOME=/opt/android-sdk/jdk` per command.
2. An overlay SDK under ~/agent-fabric-tmp: symlink each /opt/android-sdk component, make `build-tools/` and `platforms/` real directories that link the existing versions, then `sdkmanager --sdk_root=<overlay> "build-tools;35.0.0" "platforms;android-34" "platforms;android-35" "cmake;3.22.1"`. Platform 35 (flutter_appauth, jni, flutter_foreground_task) and CMake 3.22.1 (Flutter's Gradle plugin builds an empty native project) were missed at first because Gradle installs them quietly into a writable overlay; a read-only SDK fails without them (devex-tooling, REPLY 01a15a81, 2026-10-20). Gradle auto-installed `android-37.0` into the overlay; add a link `platforms/android-37 -> android-37.0`.
3. Build with `ANDROID_HOME` and `ANDROID_SDK_ROOT` set to the overlay.
4. Remove the overlay afterwards (about 650 MB).

FIXED 2026-10-21: /opt/android-sdk on develop-qzapp now matches BlueTeam-OU/InterWeave#325's pins (build-tools 35.0.0, platforms 34/35/37.0 with the android-37 link, CMake 3.22.1); devex-tooling built the passenger release APK at gzapp main c34ef900c with ANDROID_HOME=/opt/android-sdk, no overlay (REPLY 01a15ccb). The overlay recipe above is history: use it only if `tools/host/android/android-toolchain.sh --check` says the install no longer matches. A plugin bump that raises compileSdk, or an AGP bump, needs a new pin: tell devex-tooling. Open: the build warns permission_handler_android compiles against SDK 37 while both apps use `compileSdk = flutter.compileSdkVersion`.

Two traps:
- A `flutter test` started while the Gradle build runs regenerates GeneratedPluginRegistrant.java with dev dependencies, and the build then fails with "package dev.flutter.plugins.integration_test does not exist". Run nothing else Flutter in that tree during a build.
- Each build makes the Flutter migrator add `android.builtInKotlin` and `android.newDsl` lines to android/gradle.properties. Restore that file, and analysis_options.yaml, before committing. Related: [[flutter-safe-directory]].

*References: flutter-safe-directory*

*Anchors: `gzapp:apps/passenger_flutter/android/gradle/wrapper/gradle-wrapper.properties::gradle-8.14`, `gzapp:apps/passenger_flutter/android/app/build.gradle.kts::isCoreLibraryDesugaringEnabled`*

*Observed 2026-10-19 (flutter-dev)*

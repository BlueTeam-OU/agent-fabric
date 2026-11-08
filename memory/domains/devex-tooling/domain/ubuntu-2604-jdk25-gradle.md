---
role: "devex-tooling"
class: domain
topic: "ubuntu-2604-jdk25-gradle"
description: "ubuntu-latest is ubuntu-26.04 with default JDK 25; Gradle below 9.1 refuses it — a CI Android build with no setup-java breaks"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - a3c05b7d15ceecc2
---

## ubuntu-latest is ubuntu-26.04 with default JDK 25; Gradle below 9.1 refuses it — a CI Android build with no setup-java breaks

On GitHub's hosted runners `ubuntu-latest` resolves to `ubuntu-26.04` (image 20261021.x seen 2026-10-26),
whose default `JAVA_HOME` is JDK 25 (25.0.4, then 25.0.5). Gradle 8.14 refuses it: "compatible Gradle
versions for Java 25 are 9.1.0 or newer". A workflow that builds an APK without `actions/setup-java`
inherits that JDK.

Measured in gzapp: `_flutter.yml` has no setup-java and builds the release APK only on schedule/push/dispatch
(GZAPP_BUILDS_APK), so PR and queue runs stayed green while Cache warm went red two weeks running
(2026-10-26, 2026-11-02, run 41444262020; issue gzapi-org/gzapp#1185) — a red only the weekly build showed.
Fix taken as j301 (pin the JDK in CI; a Gradle/AGP upgrade instead is flutter-dev's).

**How to apply:** any Android/Gradle job on ubuntu-latest pins its JDK; when a scheduled-only build is red,
check the runner image line ("Image: ") before reading the build.

*Observed 2026-11-08 (devex-tooling)*

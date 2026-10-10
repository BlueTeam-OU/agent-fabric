---
role: "fabric-coordinator"
class: threads
topic: "shared-android-toolchain-deferred"
description: "DONE by devex-tooling (owner, 2026-10-07): the shared Android toolchain is not on my list"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 173e30587d9277ad
  - 176517b80f712ba6
---

## DONE by devex-tooling (owner, 2026-10-07): the shared Android toolchain is not on my list

Raised by flutter-dev-01 (relay seq 5253, 2026-09-26): each login installs its
own Android SDK and Gradle cache, ~9 GB per login, on a /home that had reached
99%. The owner (2026-09-26): keep the plan, don't do it now — flutter-dev-01 is
the only login using it.

Measured 2026-09-26: flutter-dev-01 `~/Android/Sdk` 3.2 GB (build-tools 35+36,
platforms 35/36/37.0, NDK 28.2.13676358, cmake, platform-tools, cmdline-tools),
`~/.gradle` 5.4 GB, no JDK of its own (system OpenJDK 25 from the template).
The coordinator login also carries `~/Android` 3.7 GB and `~/.gradle` 5.5 GB.

The plan, when a second Flutter login needs it:
- No TemplateVM needed: `/usr/local` is persistent on this Qubes AppVM (same
  private volume /dev/xvdb as /home), so the SDK goes to
  `/usr/local/share/android-sdk`, world-readable; `ANDROID_HOME` per login set
  through the fabric.
- The SDK licence is accepted by the owner, never by an agent
  (`sudo …/sdkmanager --licenses`).
- Gradle: a shared read-only dependency cache (`GRADLE_RO_DEP_CACHE`); each
  login keeps a small writable `~/.gradle` — one writable cache across users
  is unsupported.
- A different JDK is a dnf package, so it belongs in the TemplateVM (the owner's).
- Same volume as /home: the saving is de-duplication only, ~9 GB per extra login.
- Then ask flutter-dev-01 to remove its per-login copy.

Also: adb's port moved to 5137 because 5037 collided with flutter-dev-01's
Tempo port (same report).

DONE 2026-10-07: the owner says devex-tooling built the shared Android toolchain. It is off my backlog.

*Observed 2026-09-26 (fabric-coordinator)*

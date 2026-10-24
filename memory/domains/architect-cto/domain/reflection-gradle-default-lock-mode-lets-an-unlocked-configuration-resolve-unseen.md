---
role: "architect-cto"
class: domain
topic: "reflection-gradle-default-lock-mode-lets-an-unlocked-configuration-resolve-unseen"
description: "Under Gradle's default lock mode a locked configuration with no lock state yet resolves without validation and appears in no lockfile, so a guard that reads lockfiles needs LockMode.STRICT to see every configuration"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - de2a7591162463c8
---

## Under Gradle's default lock mode a locked configuration with no lock state yet resolves without validation and appears in no lockfile, so a guard that reads lockfiles needs LockMode.STRICT to see every configuration

InterWeave 2026-10-17: "resolves unvalidated and appears in no
lockfile, so the guard cannot see it" (01a15433-65f5); "The first
STRICT build failed with ':app:androidApis is locked but does not have
lock state'" (01a1544a-5ec4). InterWeave's build sets STRICT and the
no-play-services check enforces it; the field rule is for the next
Gradle project.

*Observed 2026-10-23 (architect-cto)*

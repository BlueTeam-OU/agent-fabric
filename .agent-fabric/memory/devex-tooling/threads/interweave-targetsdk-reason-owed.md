---
role: "devex-tooling"
class: threads
topic: "interweave-targetsdk-reason-owed"
description: "InterWeave tools/host/android justifies targetSdk 36 as \"Google Play's target\"; ADR-0056 (F-Droid only) removed that reason — restate it on the next touch"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ebee81aa8310bc18
---

## InterWeave tools/host/android justifies targetSdk 36 as "Google Play's target"; ADR-0056 (F-Droid only) removed that reason — restate it on the next touch

architect-cto-01 INFO 01a15386-f4f3 (2026-10-19): `tools/host/android/README.md:12` and
`tools/host/android/android-toolchain.pins:11` give "Google Play's target" as the reason for
targetSdk 36. ADR-0056 (4d9cf47f, InterWeave #301) ships on F-Droid only, so that reason no
longer binds. The number may stay (Android's foreground-service enforcement is read at the
current target; F-Droid builds need a target); the stated reason should be the platform's.
No urgency: do it with the next change to those files, e.g. alongside j164 (the ADR-0056
classpath guard). Pin shared with p2p-network-dev.

Update 2026-10-19 (INFO 01a153c4-8c4e from architect-cto-01): ADR-0057 supersedes ADR-0056 on distribution (no store, F-Droid dropped for now); its decision 2 is ADR-0056 decision 2 verbatim. j164 is unchanged in scope; its --help cites ADR-0057 decision 2.

*Observed 2026-10-19 (devex-tooling)*

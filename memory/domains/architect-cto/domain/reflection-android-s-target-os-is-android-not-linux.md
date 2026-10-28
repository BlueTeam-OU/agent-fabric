---
role: "architect-cto"
class: domain
topic: "reflection-android-s-target-os-is-android-not-linux"
description: "In Rust, Android's target_os is android, so a cfg(target_os = \"linux\") gate in our crates or in a dependency's backend silently selects the fallback branch on Android"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2fb8ca8fc745f3b2
---

## In Rust, Android's target_os is android, so a cfg(target_os = "linux") gate in our crates or in a dependency's backend silently selects the fallback branch on Android

InterWeave 2026-10-09: "Android's target_os is 'android', not
'linux', and profile-config gates on cfg(target_os = "linux") alone in
three files" (…c771e53d2972); "On target_os = 'android', if-watch
compiles its POLLING FALLBACK" (…0d936e33250e). persist.rs now uses
any(linux, android); 55 bare linux gates remained under crates/ on
2026-10-23 and no check covers them — a check over the embedded host's
graph would retire this (devex-tooling's to decide).

*Observed 2026-10-23 (architect-cto)*

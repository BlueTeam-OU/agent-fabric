---
role: "rust-ui-dev"
class: domain
topic: "gradle-task-action-captures"
description: "A Gradle task action (doLast) that names an AGP Variant, even in a message string, breaks the configuration cache; capture plain values at configuration time and run the task once with --configuration-cache"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 3a08b8446e472c6f
---

## A Gradle task action (doLast) that names an AGP Variant, even in a message string, breaks the configuration cache; capture plain values at configuration time and run the task once with --configuration-cache

In a Kotlin build script, `${variant.name}` inside `doLast { check(...) { "..." } }` makes the lambda
capture the AGP `Variant`, which holds the project services (a `JavaCompile`, a `ReferenceQueue`), and
`--configuration-cache` fails to store the task. Found by the review of BlueTeam-OU/InterWeave#404 (F1,
fixed in 371c3115): take `val variantName = variant.name` beside the other plain values before `doLast`.
A versionName set through `variant.outputs[...].versionName` does reach `SingleArtifact.MERGED_MANIFEST`
(measured on #404), so a check reading the merged manifest sees variant-API overrides.

**Why:** the plain build passes, so the defect is invisible until someone turns the cache on.
**How to apply:** for any new Gradle task, run it once with `--configuration-cache` before review; the
action may hold only Strings, Providers and other serializable values.

*Observed 2026-10-24 (rust-ui-dev)*

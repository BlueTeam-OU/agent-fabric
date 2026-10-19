---
role: "rust-ui-dev"
class: domain
topic: "vuln-ignore-entries-checked"
description: "Accepting a known vulnerability in a build-tool classpath (OSV/cargo-deny ignore) -- the entry names what was checked and when, and ends early on a new stable release"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 326fe64648330b8a
---

## Accepting a known vulnerability in a build-tool classpath (OSV/cargo-deny ignore) -- the entry names what was checked and when, and ends early on a new stable release

An OSV scan of an Android Gradle build's lockfiles found nine advisories, all on the Android
Gradle Plugin's own buildscript classpath or lint, none on a class that reaches the APK.
The policy agreed: a finding on any runtime/compile classpath of a variant is never accepted;
a build-tool-only finding may be, as an entry whose reason names the newest stable release
checked in the pinned line and its date ("AGP 9.4.1, checked 2026-10-11, no fix in 9.4.x"),
so an expiry check cannot pass an unchecked "no fix" claim; a new stable release in the line
ends the entry early. Do not force newer transitive versions onto the plugin's classpath with
constraints: it overrides what the plugin was tested with. Watch for the fixing release and
bump then.

*Observed 2026-10-15 (rust-ui-dev)*

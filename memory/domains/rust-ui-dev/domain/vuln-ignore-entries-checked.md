---
role: "rust-ui-dev"
class: domain
topic: "vuln-ignore-entries-checked"
description: "Accepting a known vulnerability on a build-tool classpath (an OSV or cargo-deny ignore): the entry says what was checked and when, and expires early on a new stable release"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 326fe64648330b8a
  - 4bf447403b4d8ccf
---

## Accepting a known vulnerability on a build-tool classpath (an OSV or cargo-deny ignore): the entry says what was checked and when, and expires early on a new stable release

An OSV scan of an Android Gradle build's lockfiles found nine advisories. All were on the Android Gradle Plugin's own buildscript classpath or on lint; none was on a class that reaches the APK.

The agreed policy:
- A finding on any runtime or compile classpath of a variant is never accepted.
- A finding on build tools only may be accepted, as an entry whose reason names the newest stable release checked in the pinned line and the date of the check (in InterWeave's osv-scanner.toml, "checked: AGP 9.4.1 2026-10-11"). That way an expiry check cannot pass a "no fix" claim nobody checked.
- A new stable release in that line ends the entry early.

Don't force newer transitive versions onto the plugin's classpath with constraints: that overrides what the plugin was tested with. Watch for the release that fixes it, and bump then.

Rechecked 2026-10-20 against InterWeave origin/main, apps/human-android/android/osv-scanner.toml lines 73 and 86. The earlier "a path is gone" flag came from the words "runtime/compile", which are not a path.

*Observed 2026-10-20 (rust-ui-dev)*

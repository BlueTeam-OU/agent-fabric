---
role: "fabric-coordinator"
class: workflow
topic: "release-changelog-semver"
description: "The owner (2026-10-10): released software we ship (first the gateway) follows Keep a Changelog 1.1.0 and Semantic Versioning 2.0.0, with the public API declared and tag = Cargo/--version = CHANGELOG section"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4e50b3f41b52e540
---

## The owner (2026-10-10): released software we ship (first the gateway) follows Keep a Changelog 1.1.0 and Semantic Versioning 2.0.0, with the public API declared and tag = Cargo/--version = CHANGELOG section

The owner, 2026-10-10, on the gateway's first release (#31): "gateway should adhere to
https://keepachangelog.com/en/1.1.0/ https://semver.org/spec/v2.0.0.html".

**Why:** the fleet pins released binaries by version and digest (gateway ADR-014); a version
whose meaning is declared and a human-readable changelog are what make a pin reviewable.

**How to apply:** for any project that tags releases: CHANGELOG.md with `[Unreleased]` and
`[x.y.z] - YYYY-MM-DD` sections and the standard groups, comparison links at the bottom; a
declared public API (for the gateway: CLI and exit codes, --version --json, control-plane
contract and plan-schema versions, descriptor and token-file protocol); tag, manifest version
and the binary's reported version agree, and the release job refuses a mismatch. Write the
rule into the project's own release docs so later releases follow it unasked.

*Observed 2026-10-10 (fabric-coordinator)*

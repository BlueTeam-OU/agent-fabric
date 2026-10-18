---
role: "rust-ui-dev"
class: domain
topic: "tests-under-umask-002"
description: "Tests of owner-only-directory code pass under umask 022 and fail under 002 with a shared primary group -- make test dirs 0700 explicitly"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8c1cbe94adee3f14
---

## Tests of owner-only-directory code pass under umask 022 and fail under 002 with a shared primary group -- make test dirs 0700 explicitly

tempfile::tempdir() honours the umask: under umask 002 with a primary group shared by other
accounts it is 0775 in that group, so code that refuses group-writable ancestors refuses the
test's own scratch. Six of my packages failed that way while passing under 022. Fix: a
per-crate helper that creates the test root 0700, and explicit modes on test config files.
Verify a suite of permission-checking code once under the other umask (e.g. `sg <shared
group>` with umask 002) as well as the default.

*Observed 2026-10-15 (rust-ui-dev)*

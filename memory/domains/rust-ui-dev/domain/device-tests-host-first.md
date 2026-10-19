---
role: "rust-ui-dev"
class: domain
topic: "device-tests-host-first"
description: "Instrumented device tests for a Rust core in an Android app -- run the same case bodies on a host stand-in of the SAME composition first, so a device failure is a platform fact"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 986a9e9bcb044c04
---

## Instrumented device tests for a Rust core in an Android app -- run the same case bodies on a host stand-in of the SAME composition first, so a device failure is a platform fact

- Put the case bodies in one test-only crate, generic over the binding, and run them on a
  host stand-in before the phone: when the stand-in passes and the device fails, the failure
  is a platform fact. On one phone that ladder surfaced, one per run: SELinux denying
  link(2), a crate panicking for want of an Android context, bionic's group answers.
- The stand-in must be the app's own composition, not a bare runtime: a case that leased
  the human endpoint passed on a bare host runtime and could never pass in the app, whose
  facade already holds that lease. Split cases by what they need ("the runtime alone" vs
  "the app's full service with a client handle").
- Shape an instrumented case as `am instrument -e case <name> -e args <base64 JSON>` with a
  JSON result copied to status keys; every status value is a string -- reading an array
  there broke the host side once.
- The release APK must not contain the case crate or the test JNI entry; enforce it with a
  dependency-graph check, not a comment.
- A test that needs the platform's facts (permissions, a control directory) gets its
  premise checked on the device first: a control that assumed files/ would be refused was
  itself wrong on a device.

*Observed 2026-10-15 (rust-ui-dev)*

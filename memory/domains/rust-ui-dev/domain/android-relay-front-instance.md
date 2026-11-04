---
role: "rust-ui-dev"
class: domain
topic: "android-relay-front-instance"
description: "Android Activity relay threads on a process-wide ask queue must carry asks out on the front instance, not their own"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ae85b8c4a9ec6c8b
---

## Android Activity relay threads on a process-wide ask queue must carry asks out on the front instance, not their own

A process-wide native ask queue (Rust side) read by per-Activity relay
threads is shared by every Activity instance. On Back, the platform starts
the instance below (onStart) BEFORE the closing one's onStop, and a relay
blocked in a timed wait keeps taking asks for up to its timeout after
onStop. An ask run on the thread's own instance lands on the wrong window:
for FLAG_SECURE, a SECURE_OFF clears the closing window and leaves the shown
one secure; an OFFLINE can secure a window the secret is not drawn in.

Rule: keep a companion `front` (set in onStart, cleared in onStop only if
`front === this`), and carry every relayed ask out on the main thread on
`front`. Never on `this`, and never just drop it after a `shown` check (that
loses it). InterWeave #313 f382d5ba (MainActivity.kt), found from
ux-designer-01's OBSERVATION 01a15b12. Related: [[android-private-dir-ancestors]].

*References: android-private-dir-ancestors*

*Observed 2026-10-21 (rust-ui-dev)*

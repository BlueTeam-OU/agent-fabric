---
role: "p2p-network-dev"
class: domain
topic: "domain-device-tests-run-in-the-app-process"
description: "Testing an in-process mobile runtime on a real device: run one generic case body in the app's own process (instrumentation) and on a host stand-in that runs the SAME composition; never a debug IPC port"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 03b0b87bb59c72bb
---

## Testing an in-process mobile runtime on a real device: run one generic case body in the app's own process (instrumentation) and on a host stand-in that runs the SAME composition; never a debug IPC port

InterWeave Stage 17 gate (c), architect-cto's DECISION 01a12770 and what followed (#258, #260):
- A debug-only IPC port in the APK was refused: it is a second adapter the shipped app never runs, its
  evidence is about a host client rather than the app's composition, and an Android ABSTRACT Unix socket has
  no filesystem permission — any app on the device could connect to the data session.
- Shape adopted: one case body generic over the binding, two runners — the host stand-in first (so a
  failure on the phone is a platform fact, not a case bug) and an instrumented runner in the app's process
  (`am instrument -e case … -e args <base64 JSON>`, results as status keys). The host only orchestrates
  (peers, relay, lifecycle, reads).
- The stand-in must run the SAME composition as the device: it ran a bare runtime while the phone's service
  ran the client facade, which already holds the `human` endpoint lease, so a case claiming that lease
  passed on the host and could never pass on the phone. Cases are tagged by what they need (the runtime
  alone vs the app's full client) and the device runner starts exactly that.
- Each `am instrument` is a fresh process: anything a multi-step case relies on across runs (the identity)
  must persist; a debug build minting a fresh identity per start breaks it.
- A release-build guard: the case crate and the test JNI entry must not reach the release graph (a cargo
  walk sees the crate; only the built APK shows the Java class).

**How to apply:** before writing a device seam, list what the app process already owns (leases, locks,
identity) and make the stand-in own the same.

*Observed 2026-10-15 (p2p-network-dev)*

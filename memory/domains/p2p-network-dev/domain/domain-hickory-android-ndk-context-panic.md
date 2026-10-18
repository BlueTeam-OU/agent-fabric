---
role: "p2p-network-dev"
class: domain
topic: "domain-hickory-android-ndk-context-panic"
description: "hickory's Android read_system_conf panics (not Errs) without an initialised ndk_context, which only android-activity sets"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 9a94d5c71a8c1f8e
---

## hickory's Android read_system_conf panics (not Errs) without an initialised ndk_context, which only android-activity sets

On Android, `hickory_resolver::system_conf::read_system_conf()` asks `ndk_context::android_context()` for the JVM. ndk-context 0.1.1 PANICS (lib.rs:72, "android context was not initialized") unless something initialised the context first.

- Only android-activity does that, on the Activity's first `android_main`.
- So a runtime started before any Activity panics: an instrumentation process, or a service restarted after process death. Measured on a Pixel 9a, 2026-10-14.
- The app cannot set the context itself. android-activity asserts that nothing initialised it before it.
- Rejected: catch_unwind. The panic hook still fires, and it races the context android-activity owns.

InterWeave's fix (#277): `host_resolver_conf()` is cfg-gated off Android, so the runtime starts with ResolverUnavailable. The DNS servers then come from the platform view (LinkProperties.getDnsServers), job j30.

*Observed 2026-10-14 (p2p-network-dev)*

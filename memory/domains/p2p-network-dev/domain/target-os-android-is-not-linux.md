---
role: "p2p-network-dev"
class: domain
topic: "target-os-android-is-not-linux"
description: "Rust's target_os for Android is \"android\", never \"linux\": every cfg(target_os = \"linux\") gate in the closure, and each dependency's platform backend, silently takes its non-Linux path on a device; audit them and build for the target…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4f69e32d997dc894
---

## Rust's target_os for Android is "android", never "linux": every cfg(target_os = "linux") gate in the closure, and each dependency's platform backend, silently takes its non-Linux path on a device; audit them and build for the target before claiming Android support

`aarch64-linux-android` has `target_os = "android"`, even though the kernel
is Linux. Code gated on `target_os = "linux"` alone compiles its fallback
there and gives no error:

- InterWeave profile-config (2026-10-09): the profile lock (O_NOFOLLOW),
  config.yaml's guarded open, and the name-service and ACL reads were
  linux-only. On a device the embedded host would refuse at the lock and
  the config load before its trust boundary was ever asked. Widened to
  `any(target_os = "linux", target_os = "android")` in a9d6e60e. The first
  real target check showed the symptom: the linux-only functions came up as
  `never used` warnings (judge_document, access_acl_of). Those warnings
  went away once the gates were widened.
- if-watch 3.2.2 (under libp2p-tcp's wildcard listener) compiles its
  netlink backend for `target_os = "linux"` only. On Android it falls back
  to polling getifaddrs every 10 s, so the runtime notices a network change
  up to 10 s late, if at all, unless the platform pushes it a view.

**How to apply:** for any crate meant to run on Android, `git grep
'target_os = "linux"'` across the crate and its first-party closure, and
check each dependency's platform backend in its source (not its README).
Treat a dead-code warning that appears only on the target as a sign of a
gate that excludes it. Code that was never built for the target is
"compile-unverified": say so until a `cargo check --target
aarch64-linux-android` has run. In InterWeave that is CI's advisory
"android check (aarch64-linux-android)" context, because this account has
no rustup target.

*Observed 2026-10-25 (p2p-network-dev)*

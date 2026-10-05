---
role: "p2p-network-dev"
class: domain
topic: "per-arch-constants-come-from-libc"
description: "Never hand-type an open(2) flag per architecture; take it from libc — CI runs x86_64 only, so no test catches a wrong arm"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4008c75f5121edb5
---

## Never hand-type an open(2) flag per architecture; take it from libc — CI runs x86_64 only, so no test catches a wrong arm

The #145 profile lock spelled O_NOFOLLOW per target_arch to avoid a libc
dependency and put aarch64 in the x86_64 arm (0o400000 — O_LARGEFILE on
arm64; aarch64's O_NOFOLLOW is 0x8000, like arm and powerpc), so the lock
followed links on arm64. Its unit test "fails if wrong for the target the
tests run on" — and CI runs ubuntu-latest x86_64 only. Found by re-review 3.

**Why:** a test is a pin only on the targets CI runs; a hand-typed ABI table
is unpinned on every other arm. libc was already compiled through tokio, so
the "no libc" purity bought nothing.

**How to apply:** take ABI constants (flags, errno — assert `libc::ELOOP`,
not 40) from `libc` as a target-gated dependency, gate the tests that use it
the same way, and check `cargo tree -i libc` that the edge adds no feature.
When removing a "no X" premise, grep for every "no X" sentence (persist.rs
and plan §16 still said it). See [[host-cargo-is-system-1-98-no-rustup]].

*References: host-cargo-is-system-1-98-no-rustup*

*Observed 2026-09-29 (p2p-network-dev)*

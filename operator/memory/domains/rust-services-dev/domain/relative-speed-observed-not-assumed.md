---
role: "rust-services-dev"
class: domain
topic: "relative-speed-observed-not-assumed"
description: A test that needs one party slower than another (slow client vs path) must observe it on the peer, never assume it from a fixed rate
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - a0150864c4b12a70
---

## A test that needs one party slower than another (slow client vs path) must observe it on the peer, never assume it from a fixed rate

A test claim "the client is slower than the path" must be made true by
construction and witnessed on the peer, not assumed from an absolute pace.
A fixed rate (64 MiB/s) that beats a debug gateway on an idle host is the
path's own speed on a loaded one (measured 50-64 MiB/s alone, load ~50 on
10 cores, 2026-11-13), and a `waits > 0` assertion then flakes ~1 in 3.

**Why:** j96, gateway PR #93 (e0a2e1a): `slow.rs` reads_slowly now stops every
AHEAD/4 until the upstream stands still (QUIET), bounds held during the
wait, and asserts the upstream stood past what the client had read.
Control: old binary 3/20 fail under 4 parallel copies; new 20/20 pass.

**How to apply:** any assertion comparing two parties' speeds, a sleep
that "must be long enough", or a rate "slower than X": replace by a pause
until the peer's observed state says so (stood still, buffer full), with a
bound that fails loudly. Reproduce a load flake with N parallel copies of
the test binary (`python3 stress.py <bin> <test> 4 5`), the pre-fix binary
copied aside as control before rebuilding. Two traps the review found (rounds 1-2, merged 7cd5f958): a pacing
schedule measured from the read's start is dead after the first pause
(elapsed is always past due) - restart it after each pause; and a wait
that can end because the fake's script ran out must say so, not blame
delivery. Every chunk read and stand-still wait is bounded (STAND_WITHIN).
Open: F3 (flood-ran-out message in beside_slow) deferred to the j95 PR.
Related: [[gateway-memory-ceilings-child-process]].

*References: gateway-memory-ceilings-child-process*

*Observed 2026-11-13 (rust-services-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "domain-a-wait-on-out-of-band-state-polls-on-a-tick"
description: "A test wait woken only by swarm events misses state a thread pushes (an accepted socket); re-read the condition on a tick too"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 0c2492db0ad21d5c
---

## A test wait woken only by swarm events misses state a thread pushes (an accepted socket); re-read the condition on a tick too

A test's `until` that drives swarms with `select!` and re-reads its condition only
after an event will miss any conjunct that a thread outside the swarms changes
(e.g. a std listener's accept thread pushing sockets into an `Arc<Mutex<Vec>>`):
if that push lands after the last swarm event, the loop sleeps until the next
event — in dcutr.rs that was the held dial's own 10 s handshake timeout, so the
"had not failed yet" assertion fired (j83, seen once in a full suite under load).

Fix the helper, not the call site: cap each step at a short recheck tick
(`step(remaining.min(RECHECK))`, 50 ms). Reproduce such a race by DELAYING the
out-of-band push (500 ms sleep before the push): the unfixed wait failed 3/3 with
the exact reported event sequence, the fixed one passed 5/5. Pinning to one CPU
with busy loops did NOT reproduce it (0/40) — widen the real window instead, see
[[domain-a-test-waits-for-the-state-it-presumes]].

Commit: 86cba937 on develop-qzapp/p2p-network-dev-02/feat/j83-dcutr-rs-2026-a-late-failure.
The rust-ui-dev e2e harnesses' `until` loops already sleep 50 ms per round.

*References: domain-a-test-waits-for-the-state-it-presumes*

*Observed 2026-10-27 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "domain-a-test-waits-for-the-state-it-presumes"
description: a test that drives an event from another thread must wait for the state it assumes; widen the real window to prove a race that a loop cannot reproduce
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 0705382e19986fbe
---

## a test that drives an event from another thread must wait for the state it assumes; widen the real window to prove a race that a loop cannot reproduce

A route begins when the sender learns the far end accepted (the runtime's `sent_to`, and the fake's). So the far end can hold the message before the sender holds its route. A path change driven in that window is where the route begins (previous None), not a change from it. android-e2e-cases' previous-path test drove the change from the desktop thread once it held the message. It passed by timing in #294's queue build (devex-tooling OBSERVATION 01a14874-4b4f, 2026-10-17).

The fix is in the test, not the model: the fake gained `routed_sessions(peer)`, and the test waits on it (2158d8cd, 11d34aa8 on j36's branch). Changing the fake to record the route before delivery would have made it differ from the runtime.

How it was proved: an unwidened loop passed 800 of 800, one CPU included, so a loop proves nothing. A temporary 300 ms sleep in the real window (between the delivery and recording the route) reproduced CI's exact output 10 of 10; with the fix, 0 of 10. A waker that fires inside the delivery hits the window on every run, so the conformance test pins it with no timing.

**How to apply:** when a test drives an event from one thread that assumes a state another thread records, find the observable for that state and wait on it, bounded. To prove such a race, widen the real window, never build a lookalike. Read the runtime before "fixing" the fake.

*Observed 2026-10-17 (p2p-network-dev)*

---
role: "rust-ui-dev"
class: domain
topic: "device-case-reads-while-connected"
description: "an e2e assertion on connection-scoped UI state (route indicator) must read it while the peer is still connected; a phone's case ends its runtime when it answers"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1497e54e3d812c93
---

## an e2e assertion on connection-scoped UI state (route indicator) must read it while the peer is still connected; a phone's case ends its runtime when it answers

Connection-scoped view state (a route indicator, a "connected" badge) is
removed when the peer disconnects — InterWeave's ui-model drops the path
on PeerDisconnected. An e2e test that reads it after the remote side's
case has finished passes on host stand-ins (they stay up to the end) and
fails on a real phone, whose instrumented case stops its runtime the
moment it answers. Measured 2026-10-16 on a Pixel 9a: both human_chat
device cases timed out at "D's route indicators set" after every message
had crossed; fixed in InterWeave de4adbb8 by reading each indicator
inside the per-side loop, while that side's case still runs, and
asserting on what was read.

**Why:** a stand-in that outlives the case is a different lifecycle from
the device; the difference hides exactly this class.
**How to apply:** for each assertion on state tied to a live peer,
place the read before anything that can end that peer (the case's
answer, a kill, a restart), and say in a comment why the read sits
there. Related: [[device-tests-host-first]], [[e2e-waits-from-dependency-cadence]].

*References: device-tests-host-first, e2e-waits-from-dependency-cadence*

*Observed 2026-10-16 (rust-ui-dev)*

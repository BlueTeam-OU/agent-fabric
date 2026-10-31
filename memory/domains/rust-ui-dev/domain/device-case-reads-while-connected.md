---
role: "rust-ui-dev"
class: domain
topic: "device-case-reads-while-connected"
description: "an e2e assertion on connection-scoped UI state (route indicator) must read it while the peer is still connected; a phone's case ends its runtime when it answers"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1497e54e3d812c93
  - 81a8b3063ea29d21
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

The same lifecycle breaks the last exchange too (2026-10-20, reflection; MESSAGE-IDs
01a159e8-74ca, 01a159e9-884a, 01a15a59-d014). A device case that reads the peer's last answer,
returns, and stops its runtime can lose its acceptance of that answer on the closing
connection -- which a transport may report as "outcome unknown" and is right to -- so the host
side waits for a confirmation that never comes. Seen in two cases (a paths case, a chat case).
Fix: the host side's final requirement is met while the device case still runs, then the host
sends an explicit close, and the device case returns only when it sees that close (through
the app's own facade, if that is how it reads). An APK built before the close keeps the old
race, so host side and APK must both carry it.

Third and fourth time, 2026-10-24 (reflection; MESSAGE-IDs 01a16ddc-0dcd, 01a16df2-f595,
01a16e0f-30e5): two-phone cases that returned the moment they saw the connection stopped
their runtime ~50 ms later, before the other phone's case had read it (both directions), and a
pair case required its close to be accepted while the far side ended on reading the close. So
the rule is general: a side never ends on what it saw while the other side still has to see
something; it holds the connection (here 5 s, failing if it drops) or waits for the other
side's explicit close.

*References: device-tests-host-first, e2e-waits-from-dependency-cadence*

*Observed 2026-10-16 (rust-ui-dev)*

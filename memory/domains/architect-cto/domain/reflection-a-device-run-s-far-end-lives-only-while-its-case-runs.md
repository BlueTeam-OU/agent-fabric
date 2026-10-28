---
role: "architect-cto"
class: domain
topic: "reflection-a-device-run-s-far-end-lives-only-while-its-case-runs"
description: "In an instrumented two-device run the far end's runtime lives only while a case of its own runs, so a control window or a wait on the far side must be held open by a far-end case spanning it; a host stand-in whose runtime outlives a case…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 094fbc6296a86689
---

## In an instrumented two-device run the far end's runtime lives only while a case of its own runs, so a control window or a wait on the far side must be held open by a far-end case spanning it; a host stand-in whose runtime outlives a case cannot show that failure, and a control that could not fail is no control

Two failures of one shape on InterWeave's Stage 21 phone rows
(2026-10-24/25, p2p-network-dev-02): row 1's far-end case ended on
seeing the connection, its process was the runtime, the connection
closed 49 ms later and the dialler's redial fell into backoff; the host
stand-ins never showed it because their runtime outlives a case. Then
#421's "neither source" control ran its 15 s window with no far-end
case up, so on a phone nothing listened and three control rows could
not fail (the review's F1). The fix each time: the far end's case holds
the device up and listening through the dialler's whole window, the
host asserts it outlived the window, and the file says which runs were
a control. The re-run measured 12/12 with the control live.

**Why:** on a device the app's runtime is the instrumentation's; the
moment the far-end case returns, the peer is gone, and a window that
measures "nothing connected" against an absent peer measures nothing.

**How to apply:** when a device row has a far side, require a far-end
case that spans every window the near side measures, an assertion that
it did, and one mutation that fails the control; read a stand-in pass
as proof of the case logic only, never of device timing; when a review
finds a control vacuous, the run file says so and the stage gate waits
on the re-run even if the PR lands.

*Observed 2026-10-25 (architect-cto)*

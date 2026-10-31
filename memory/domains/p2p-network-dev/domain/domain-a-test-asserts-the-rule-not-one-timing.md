---
role: "p2p-network-dev"
class: domain
topic: "domain-a-test-asserts-the-rule-not-one-timing"
description: "A timing flake is fixed by asserting what the rule permits and keeping the broken case failing inside the run, never by widening a timeout alone; prove the flake under CPU load before and after, and re-run the mutation"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 280d57c45db824c9
---

## A timing flake is fixed by asserting what the rule permits and keeping the broken case failing inside the run, never by widening a timeout alone; prove the flake under CPU load before and after, and re-run the mutation

Two CI flakes reported by rust-ui-dev-01 in InterWeave, fixed in the same way:

1. The live_dns test of the held resolver event (j49) expected exactly [start, first view, latest]. That
   sequence holds for only one ordering of the runtime's select arms, and CI failed it three tries in a row.
   The rule is "one held, the latest", and it permits three drains:
   - [start, latest]
   - [start, first, latest]
   - [start, strict, latest]
   The fix reads until the latest event arrives, then asserts the set of legal sequences.
2. ipc-server's `an_answered_probe_keeps_the_connection` set a 100 ms pong window with max_missed 1, and a
   loaded host read a pong late (BrokenPipe). Widening only the window would have made the test vacuous: with
   three pings at 50 ms, any window longer than the run passes on a server that ignores every pong. The fix
   widens the window to 1 s and lengthens the run to 3 s of answered pings, so an untaken pong still closes
   the connection inside the run. With the server's pong handling removed, the test fails in about 1.1 s. The
   unanswered-probe case keeps its tight window, because there the close is the assertion.

Proving it: run the old and new test binaries N times beside 4 CPU-burning loops. In the live_dns case the old
test failed 1 of 40. My first rewrite also failed 1 of 40, because it still forbade a legal ordering. The final
version failed 0 of 60.

**How to apply:** for a flaky timing test, first write down what the rule permits and assert that set. If a
bound must widen, check that the broken implementation still fails within the test's run. Then mutate the rule
(keep the oldest held event, drop the pong handling) and watch the fixed test fail.
Related: [[domain-a-test-waits-for-the-state-it-presumes]], [[assertions-that-cannot-fail]].

*References: assertions-that-cannot-fail, domain-a-test-waits-for-the-state-it-presumes*

*Observed 2026-10-22 (p2p-network-dev)*

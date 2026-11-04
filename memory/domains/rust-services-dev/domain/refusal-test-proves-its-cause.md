---
role: "rust-services-dev"
class: domain
topic: "refusal-test-proves-its-cause"
description: A test that a network path is refused must assert why it failed (elapsed time against the timeout, a counter on the intended drop rule), or a missing route or a RST passes it
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a5ff04ac060d33c
---

## A test that a network path is refused must assert why it failed (elapsed time against the timeout, a counter on the intended drop rule), or a missing route or a RST passes it

In InterWeave's netns harness (two NATs, the relay in a third namespace), the "direct dial
is refused by the NAT" assertion passed for the wrong reasons:
- The core had no route to the private ranges, so ICMP net-unreachable failed the dial in
  about 10 ms.
- A probe aimed at the NAT's own address hit its INPUT path, which answered with a RST.

The forward-drop rule the test was about was never reached. A review-class judgement caught
it by timing alone: about 10 ms against DIAL's 3 s.

Fixed by p2p-network-dev-02 (1c389d3e): the core routes the ranges, each NAT's forward
chain ends in `counter drop`, and the test requires the dial to end on DIAL with the far
NAT's counter risen. Two mutations prove it: NAT forwarding inbound fails the test, and
removing the core's routes fails it with "refused in 342µs, not by NatB's drop".

**How to apply:** a negative network assertion checks:
1. the kind of failure (timeout or refused or unreachable);
2. the elapsed time against the mechanism it claims (a drop costs the full timeout);
3. a counter on the rule meant to fire.
Run a live control (the same dial from the permitted side connects) and a mutation that
moves the refusal elsewhere.

*Observed 2026-10-22 (rust-services-dev)*

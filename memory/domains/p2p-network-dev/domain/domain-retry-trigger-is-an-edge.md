---
role: "p2p-network-dev"
class: domain
topic: "domain-retry-trigger-is-an-edge"
description: "A retry made due 'at once' by a condition must fire on the condition BECOMING true after the attempt was admitted (an edge), never on it simply holding (a level), or a failure that persists under that condition loops"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - ce0f68766d2938ec
---

## A retry made due 'at once' by a condition must fire on the condition BECOMING true after the attempt was admitted (an edge), never on it simply holding (a level), or a failure that persists under that condition loops

InterWeave #247: a circuit dial that failed at its relay hop should be retried at once when the relay comes
up. The first wording, "due at once when the relay is connected at settlement", is level-triggered: a cancel
that persists WITH the relay up (the client's push capacity, a class-gated handler) would re-dial
immediately, forever. Built instead: due at once only when a direct connection to the relay was established
AFTER the dial was admitted (`OpenConnection.since_ms >= ticket.admitted_at_ms`) — the restart race; a relay
already up at admission keeps the ordinary escalating delay. Tests: relay came up → due at once; the control
(relay already up) waits; two hop failures escalate.

**How to apply:** for every "retry now when X" rule, write the counter-example where X is already true and
the failure repeats; if the rule fires there, make it compare the time X became true against the attempt's
admission. Related: [[domain-libp2p-relay-circuit-canceled-is-the-hops]].

*References: domain-libp2p-relay-circuit-canceled-is-the-hops*

*Observed 2026-10-15 (p2p-network-dev)*

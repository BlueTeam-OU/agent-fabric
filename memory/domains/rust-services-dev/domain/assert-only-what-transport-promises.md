---
role: "rust-services-dev"
class: domain
topic: "assert-only-what-transport-promises"
description: "A load test asserts only what the transport's contract promises (exactly-once, bounds); order and drop counts it does not promise are reported as measurements, and a request asking for more is answered before code"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1e3f137fe4b513cc
---

## A load test asserts only what the transport's contract promises (exactly-once, bounds); order and drop counts it does not promise are reported as measurements, and a request asking for more is answered before code

architect-cto's j60 request asked that a burst through InterWeave's bridge be "every
notification emitted in order, none lost", with the daemon's drop count asserted, for
broadcast as well as direct. The contract (ADR-0055, AUTOMATED-CLIENT.md §2) promises
neither:
- Broadcast order was not preserved in 1 run of 13.
- The ingress bucket drops silently: no refusal, no log, no counter.

An order assertion would be flaky by construction, and a drop-count assertion would have
nothing to read. architect-cto confirmed "my request asserted more than the transport
promises" (REPLY 01a16321).

What held:
- direct: every accepted send notified exactly once, with no loss and no duplicate;
- broadcast: delivered ≤ the bucket's bound over the elapsed time, each delivered one
  exactly once, and sent minus delivered reported as the silent drop;
- pull: fills to its bound, `paused`, no eviction, a direct sent while paused refused
  Overloaded, receive in queue order.

Order and refusal counts were reported, not asserted.

**How to apply:** before writing a load or failure assertion, find the contract sentence
that promises it. Without one, measure and report it. Send an OBSERVATION back to the
requester with the replacement assertions before building, not after a flaky CI.

*Observed 2026-10-22 (rust-services-dev)*

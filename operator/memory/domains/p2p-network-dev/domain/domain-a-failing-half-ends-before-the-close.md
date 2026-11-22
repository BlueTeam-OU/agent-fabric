---
role: "p2p-network-dev"
class: domain
topic: "domain-a-failing-half-ends-before-the-close"
description: "In a two-party test, the far side's closing send may meet a half that already failed and ended; record the close's outcome, never expect() it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 88f6449701dc070d
---

## In a two-party test, the far side's closing send may meet a half that already failed and ended; record the close's outcome, never expect() it

A half that FAILS returns before it waits for the close, so its session is gone when the other side's close arrives (InterWeave: the fake's `RemoteEndpointUnavailable`, the paths fake-pair test in CI on #458). Asserting the close (`.expect("D closes")`) turns a correct FAIL verdict into a timing-dependent panic. The close's outcome is recorded beside the verdict (`keys::CLOSE`), and a passing half needs the close anyway because it waits to read it. A sleep before the close reproduced the panic every run; fixed in #459 (dfcb8c87, 95fe97ea, merged 81d72849). See [[domain-a-two-party-case-ends-on-an-explicit-close]].

*References: domain-a-two-party-case-ends-on-an-explicit-close*

*Observed 2026-10-26 (p2p-network-dev)*

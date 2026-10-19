---
role: "p2p-network-dev"
class: domain
topic: "domain-event-stream-owes-current-state"
description: "A client contract that delivers state only as CHANGE events never shows a state that was true from the start, or true again after a reconnect: owe the current value at route begin and at return"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 2b6166e94cc144db
---

## A client contract that delivers state only as CHANGE events never shows a state that was true from the start, or true again after a reconnect: owe the current value at route begin and at return

A client-facing event stream that reports a state (a peer's path: direct / relayed) only when it CHANGES
leaves the client blind to a state that held from the first moment — the common NAT case of a peer reached
only through a relay — and again after a disconnect clears the client's view and the peer comes back on the
same path. Nothing changed, so nothing is said, and the indicator stays empty forever. "Unknown shown as
unknown" is then correct behaviour and still a contract gap.

Found building InterWeave's real relay pair (j6, #245/#248): LOCAL-CLIENT.md owed PeerPathChanged only on a
change; architect-cto ruled a notice with `previous` absent at route begin (`route_established`) and on a
routed peer's return (`reconnected`), IPC minor 2.4.

**How to apply:** for any state the client mirrors, ask three moments, not one: when the subscription/route
begins, when the state changes, and when the client's view was cleared (disconnect, restart) and the source
returns. A test for the first and third uses a topology where the state never changes (relayed from the
first connection). Related: [[domain-event-widening-gates-the-stream]].

*References: domain-event-widening-gates-the-stream*

*Observed 2026-10-15 (p2p-network-dev)*

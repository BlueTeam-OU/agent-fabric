---
role: "p2p-network-dev"
class: solution
topic: "interweave-broadcast-ingress-drops-silently"
description: "InterWeave's per-peer broadcast ingress bucket (burst 32, 120/min) drops a burst silently at the receiver; direct answers Overloaded; a clean stop answers ShuttingDown"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3e27da582fc3453e
---

## InterWeave's per-peer broadcast ingress bucket (burst 32, 120/min) drops a burst silently at the receiver; direct answers Overloaded; a clean stop answers ShuttingDown

Measured 2026-10-19 on two loopback daemons at main 441361da (tests/fleet-carrier, j90):
- Broadcast: 200 published in a burst, 34-37 delivered. The receiver's per-trusted-peer broadcast ingress bucket (crates/transport/runtime/src/ingress.rs: burst 32, 120/min, global 256 / 1200/min) drops the rest before local delivery, as ADR-0026 says. The sender gets no refusal, there is no log line even at debug, and there is no counter (ipc.events_dropped_total is omitted). Without the bucket in mind the loss looks like a queue or gossip fault: the client queue of 256 is never reached.
- Direct: the same burst is answered Overloaded past the bucket (ENDPOINTS.md admission step 3). Retried under the same id, all 40 landed (33 retries).
- A clean daemon stop closes the IPC session with ShuttingDown, and every later call on it answers ShuttingDown, not BackendUnavailable. A client's "session gone, re-open" must match both.
- A second same-uid daemon on a taken listen port starts and stays up (SO_REUSEPORT), as in [[domain-free-port-same-port-reuseport]].

*References: domain-free-port-same-port-reuseport*

*Observed 2026-10-19 (p2p-network-dev)*

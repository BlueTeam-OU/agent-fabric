---
role: "p2p-network-dev"
class: solution
topic: "interweave-session-loss-errors"
description: what an IPC session answers when its InterWeave daemon goes away — ShuttingDown on SIGTERM, BackendUnavailable on SIGKILL
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f7493feb758d517c
---

## what an IPC session answers when its InterWeave daemon goes away — ShuttingDown on SIGTERM, BackendUnavailable on SIGKILL

Measured 2026-10-19 (tests/automated-client, a_daemon_gone_under_a_live_client_is_reopened_either_way, 4db37607). After a clean daemon stop (SIGTERM), the next call on the old IPC session answers exactly `ShuttingDown`. After SIGKILL it answers exactly `BackendUnavailable`. Either way a client opens a fresh session (lease and joins). A client's send loop must treat a failed reconnect as a retried attempt, not fall through to a send on no session: that answers `EndpointNotRegistered`, which no retry mends.

*Observed 2026-10-19 (p2p-network-dev)*

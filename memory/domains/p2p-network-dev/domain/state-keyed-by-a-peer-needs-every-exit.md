---
role: "p2p-network-dev"
class: domain
topic: "state-keyed-by-a-peer-needs-every-exit"
description: Before landing any map or queue keyed by a peer, list each way that peer can leave (disconnect, trust revoked, session ended) and give each one a removal and a test
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - ecfee0762c5111d9
---

## Before landing any map or queue keyed by a peer, list each way that peer can leave (disconnect, trust revoked, session ended) and give each one a removal and a test

State a node holds about a remote peer is easy to add and easy to forget to remove.

Three review findings in one month had this shape:
- **Reply routes (#190):** a session's routes were never forgotten.
- **Path notices (#192):** a pending path notice outlived its peer's disconnect.
- **Learned offers:** the discovery learned map kept an untrusted offer after set_trust (see [[discovery-relearn-holds-a-newly-allowed-peer]]).

Each worked on the path that adds the entry. None had a removal on the path where the peer goes away.

**Why:** the reasoning stops at the insert. Removal lives on another event (disconnect, trust change, session close) that the author is not looking at. The leak is unbounded per peer churn, or a revoked peer keeps a privilege.

**How to apply:** for each new peer-keyed structure:
- Enumerate the exits: disconnect, trust revoked or narrowed, session or lease ended, restart.
- Give each exit its removal, and a test that drives that exit over the real wiring with a control that the entry existed.
- Write the end of the entry's life into the contract sentence too. A route or notice with no stated end is a finding.

*References: discovery-relearn-holds-a-newly-allowed-peer*

*Observed 2026-10-22 (p2p-network-dev)*

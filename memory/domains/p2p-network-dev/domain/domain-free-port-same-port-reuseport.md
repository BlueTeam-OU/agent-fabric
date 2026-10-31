---
role: "p2p-network-dev"
class: domain
topic: "domain-free-port-same-port-reuseport"
description: "two bind-port-0 \"free port\" asks in a row can return the same port; libp2p-tcp's SO_REUSEPORT lets both daemons bind it, and each one's dial to the other is stripped as its own listen address (NoAddresses)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 98150fa31bc82b32
  - a4d5740a7e9ea465
---

## two bind-port-0 "free port" asks in a row can return the same port; libp2p-tcp's SO_REUSEPORT lets both daemons bind it, and each one's dial to the other is stripped as its own listen address (NoAddresses)

- **Mechanism.** Picking a port by binding port 0 and releasing it can answer the same port twice in a row. libp2p-tcp 0.45 listens with SO_REUSEPORT, so two daemons of one uid both bind it. libp2p-swarm 0.48's `dial` removes any address equal to one of its own listen addresses, so each daemon's dial to the other ends synchronously in `NoAddresses`.
- **What it looks like.** InterWeave logs it as "reconnect refused class=dial_failed" on BOTH daemons right at start, then "no_known_address" (the route is gone from the book). The pair never connects. A test waiting 30 s fails with B's send stuck on PeerUnknown/NoNetworkPath.
- **Seen:** desktop-e2e human_app retention test, #276 PR run 38523588747 (2026-10-14). Reproduced every time by forcing both daemons onto one port.
- **Do not confuse with** the EADDRINUSE reuse-dial gap ([[domain-libp2p-reuse-dial-eaddrinuse]]). That one is an asynchronous dial failure. Also, DiscoveryReconnect dials use PortUse::New.
- **Fix (2026-10-15, e8a56382 on #280):** `interweave_test_support::net::free_port` remembers every port it has answered in the process and keeps a repeated port bound while it asks again.
- **Diagnose by** the error text the composition root drops: `DialRefusal::Backend("Dial error: no addresses for peer.")`.
- **Second shape, same mechanism (2026-10-20, PR #319):** any test-port picker that answers from the kernel's port-0 range (ip_local_port_range) can hand out a port that a same-account port-0 listener with SO_REUSEPORT is then given before the answer is bound. They share it silently. A per-process set or a cross-process claim cannot see a port-0 listener, because it is not a caller. The class fix is to answer only below the range's low bound (from 1024, random start, bind-probed, claimed). On Linux, read the range or panic: a guessed default lower than the host's reopens the overlap. What stays open: a same-account SO_REUSEPORT binder whose port did not come through the claims, which shares silently, and another account, whose bind fails loudly because REUSEPORT needs one uid.
- **A test that listens on a "free" port to prove a skip** must take that port from the claiming picker. An unclaimed one can be another process's answer.

*References: domain-libp2p-reuse-dial-eaddrinuse*

*Observed 2026-10-20 (p2p-network-dev)*

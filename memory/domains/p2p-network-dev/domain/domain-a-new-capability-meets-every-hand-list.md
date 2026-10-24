---
role: "p2p-network-dev"
class: domain
topic: "domain-a-new-capability-meets-every-hand-list"
description: "Adding an enum variant (a capability, a method) — every exhaustive match compiles it in, but a hand-written array of variants silently drops it; grep for the sibling variants"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - baf3d5c6cd264a81
---

## Adding an enum variant (a capability, a method) — every exhaustive match compiles it in, but a hand-written array of variants silently drops it; grep for the sibling variants

Adding `AdminCapability::Peers` (j54, ADR-0062) compiled cleanly everywhere a
`match` was exhaustive, but the IPC server's admission set was built from a
hand-written array `[Status, Endpoints, Shutdown, Trust].filter(holds)`
(`crates/local/ipc-server/src/connection.rs`, `admin_grants`), so a connection
the hello GRANTED `admin.peers` had every address method refused
`CapabilityDenied`. Unit tests of dispatch passed because they called
`dispatch::admin` directly, below admission; only the daemon e2e through
`transportctl` caught it.

Fix of the class, not the instance: read the set whole
(`LocalAdminPort::capabilities()`), never re-enumerate variants. When adding a
variant, grep for its SIBLINGS listed together (`Trust]`, `C::Trust`) — an
array literal of variants is a match the compiler does not check. And test a
new method through the admission layer (server-level hello + request), not only
its dispatch arm, with a control that is refused without the grant.

*Observed 2026-10-22 (p2p-network-dev)*

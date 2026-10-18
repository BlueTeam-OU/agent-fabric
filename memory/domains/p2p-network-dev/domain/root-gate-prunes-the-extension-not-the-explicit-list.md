---
role: "p2p-network-dev"
class: domain
topic: "root-gate-prunes-the-extension-not-the-explicit-list"
description: "A dial-time address rule in libp2p belongs in a wrapper around the ROOT behaviour's handle_pending_outbound_connection (swarm 0.48 calls it once; its return is the extension); it never sees a DialOpts explicit .addresses() list, so every…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 91c7321ed8234956
---

## A dial-time address rule in libp2p belongs in a wrapper around the ROOT behaviour's handle_pending_outbound_connection (swarm 0.48 calls it once; its return is the extension); it never sees a DialOpts explicit .addresses() list, so every store that dials explicitly needs its own learn-site check — and libp2p-identify 0.48 keeps a 100-peer raw listen_addrs cache

libp2p-swarm 0.48.0 `Swarm::dial` makes ONE call to the root behaviour's
`handle_pending_outbound_connection`; on `Ok(addrs)` with
`extend_addresses_through_behaviour()` it appends them, on `Err` the dial is
`DialError::Denied`. So a wrapper around the root can prune or deny every
behaviour-contributed address; a sibling behaviour's hook cannot, because it
never sees what the others return. Measured on real sockets (InterWeave
RootFunnel, 2026-09-22): control opens the socket, wrapped opens none.

What the root funnel does NOT cover: the dial's explicit list. A store that
builds `DialOpts::peer_id(p).addresses(vec![a])` (an AutoNAT server list, a
relay reservation address — relay client 0.21/0.22 dials the relay with an
explicit address plus extension) reaches a socket unpruned, so the rule must
also hold where that store learns.

Stores the application's own book does not own, all fed by peers:
libp2p-identify 0.48.0 caches 100 peers' raw `listen_addrs` by default and
returns them from its pending-dial hook (`with_cache_size(0)` closes it);
request-response 0.30 keeps `PeerAddresses` from `NewExternalAddrOfPeer`;
Kademlia's table; mDNS's record store (and a scope wrapper that forwards its
pending-dial hook leaks it into every other behaviour's dials).

**How to apply:** before claiming "the book is the only address store", list
every enabled behaviour's stores and doors; enforce the class rule twice —
root funnel for the extension, learn-site for each explicit-dial store; deny
at the root only when the funnel removed something and nothing survived
(SPIKE-004: the Swarm discards a behaviour dial's denial, so a counter is the
only witness). Related: [[enumerate-a-behaviours-toswarm-emissions]],
[[libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr]].

*References: enumerate-a-behaviours-toswarm-emissions, libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr*

*Observed 2026-10-18 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "replacing-a-libp2p-behaviour-leaks-its-tasks"
description: before swapping a libp2p behaviour at runtime, check what its Drop stops — tokio JoinHandles detach, so spawned tasks outlive it
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - cf4e069e2f699ee3
---

## before swapping a libp2p behaviour at runtime, check what its Drop stops — tokio JoinHandles detach, so spawned tasks outlive it

A libp2p behaviour that spawns tasks through tokio holds `JoinHandle`s, and dropping a
`JoinHandle` DETACHES the task — it does not abort it. `libp2p-mdns` 0.49 has no `Drop`
and aborts an interface task only on `IfEvent::Down`, so a dropped behaviour's task kept
its multicast socket (bound `SO_REUSEPORT`), kept querying and kept answering beside the
replacement's: measured two answers per query after a swap, one with an `impl Drop`
aborting `if_tasks` (InterWeave ADR-0053 rule 5, A 2026-09-26; commits a302af30, c42dcd4c).

Two more facts a swap needs, both measured on that change:
- a fresh behaviour learns listen addresses only from `FromSwarm::NewListenAddr`, which the
  Swarm never repeats — re-tell it every active listen address before the first poll, or
  it announces nothing;
- drop the old one BEFORE the fresh one is first polled (plain assignment of an unpolled
  behaviour does it), or two answerers overlap.

How to measure a Drop without the crate exporting its Abort trait: a test `Provider` whose
`spawn` wraps each task in a future holding a drop-recording guard; read the drops before
the runtime shuts down (shutdown drops every future), feed the task nothing that ends it
on its own, and check it is red with the Drop removed.

Related: [[libp2p-relay-022-release-frees-the-connection]].

*References: libp2p-relay-022-release-frees-the-connection*

*Observed 2026-09-26 (p2p-network-dev)*

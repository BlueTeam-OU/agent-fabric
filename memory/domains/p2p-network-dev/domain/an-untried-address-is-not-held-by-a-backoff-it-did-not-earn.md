---
role: "p2p-network-dev"
class: domain
topic: "an-untried-address-is-not-held-by-a-backoff-it-did-not-earn"
description: "A per-peer dial backoff set by a stale address's failure must not refuse a freshly learned, never-tried address of the same peer — and the refusal usually lives at TWO sites (the retry scheduler and the admission check); placeholder dials…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6f8bf81d29e80e3e
---

## A per-peer dial backoff set by a stale address's failure must not refuse a freshly learned, never-tried address of the same peer — and the refusal usually lives at TWO sites (the retry scheduler and the admission check); placeholder dials with no address stay bound by the backoff

The restart case: a peer comes back on a new port; this node first dials the
stale cached address, fails, and puts the PEER in backoff (30 s base); the
fresh address arriving from static bootstrap or discovery a moment later is
then refused "peer in backoff". InterWeave main failed to connect within
10 s in 5 of 6 runs (same port across restarts: 6 of 6 fine).

The ruling named one site (make the retry due when a new address is learned);
implementing it showed a second: admission (`ConnectionPolicy::admit`)
refused the scheduler's dial with `PeerBackoff`. Fix at both: an address with
no record of its own makes the retry due and is admitted once under the
peer's backoff; its own dial then settles a record. After: 6 of 6 in ~17 ms.
Dials that carry no address (Kademlia query, AutoNAT probe, relay
reservation, DCUtR) must stay bound by the peer backoff — guarded by an
`is_empty()` conjunct whose removal fails its test.

**How to apply:** when a backoff is keyed coarser than the thing that failed
(peer vs address), list every site that enforces it before declaring the
fix; prove it by failure rate on main vs branch with each half mutated away.
Stated limit: admission reads a lock-free snapshot, so two concurrent manual
admissions of one untried address both pass.

*Observed 2026-10-18 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "libp2p-relay-022-limiter-and-forced-enable"
description: "libp2p-relay 0.22.0 server: the default rate limiters are token buckets (60 per IP refilled one a minute, 30 per 2 min per peer, reservations and circuits alike), not 'N per minute'; and the server forces Status::Enable, so it grants…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f16f498d31cfde0d
---

## libp2p-relay 0.22.0 server: the default rate limiters are token buckets (60 per IP refilled one a minute, 30 per 2 min per peer, reservations and circuits alike), not 'N per minute'; and the server forces Status::Enable, so it grants reservations before AutoNAT verifies an address — clients refuse those address-less reservations but they count against the relay's ceiling

Read (behaviour.rs:125-160, rate_limiter.rs:70-124) and measured on SPIKE-004
phase B, 2026-09-26:

- **Rate limit is a bucket.** `Config::default` builds `GenericRateLimiter
  {limit 60, interval 60 s}` per source IP and 30 per 120 s per peer, for
  reservations and circuits alike. 120 asks from one address: 60 accepted,
  the rest `ResourceLimitExceeded`, none in the next 4 min; 4 min later 10
  fresh dialers got 4. Consequence: peers behind one CGNAT/shared address get
  60 circuits, then one a minute.
- **Serves before verification.** The server forces `Status::Enable`, so it
  answers reservation requests before AutoNAT confirms any external address;
  the reservation it grants carries no address, the client refuses it, but
  the relay counts it until the connection closes. A client re-ask on the
  same connection reads as renewal (skips the per-peer ceiling), so the TOTAL
  fills with phantoms: ceiling 2 denied every ask from 6.8 s to 90.5 s, first
  usable reservation at 168 s; control at ceiling 3 denied nobody.
- Cost measured: ~56 KB + one fd per reservation, ~37 KB per circuit.

**How to apply:** quote the limiter as "burst N, refill one per interval";
size a relay's budget for shared source addresses; gate hop service on a
verified address per request in a wrapping handler (see
[[libp2p-facts-from-the-hop-gate-and-keepalive]]) rather than trusting the
crate's status. Related: [[libp2p-relay-022-release-frees-the-connection]].

*References: libp2p-facts-from-the-hop-gate-and-keepalive, libp2p-relay-022-release-frees-the-connection*

*Observed 2026-10-18 (p2p-network-dev)*

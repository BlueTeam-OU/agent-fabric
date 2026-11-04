---
role: "p2p-network-dev"
class: domain
topic: "a-backoff-the-host-earned-offline-is-lifted-on-a-network-addition"
description: "Dial failures while the HOST had no usable network put every peer and relay into backoff they did not earn; when the network gains an address, lift the gate's per-peer backoff for every classified peer and make relay asks due, at most…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 25cffb7c0a83312c
---

## Dial failures while the HOST had no usable network put every peer and relay into backoff they did not earn; when the network gains an address, lift the gate's per-peer backoff for every classified peer and make relay asks due, at most once per peer per lift floor, because RA prefixes, VPN and Wi-Fi flaps make additions repeat

A peer backoff is meant for a peer that refused or failed. A dial that
failed because this host was offline says nothing about the peer. After an
offline → online change, every peer the host tried meanwhile sits 30–60 s
or more in backoff for nothing. Built for InterWeave's network-change
binding (#250, ADR-0011 amendment "A network addition lifts the per-peer
backoff, once per lift floor"):

- **Making the relay reservation ladder due was not enough** (measured).
  The ask fired at once and failed at once, because the offline dial had
  also put the relay PEER in the dial gate's peer backoff. The lift must
  cover the gate's peer backoff for every classified peer, infrastructure
  included. The scheduler's redial is due for data-plane peers only; an
  infrastructure peer's redial is its adapter's. Unauthorized peers get
  nothing. Address quarantines are untouched, because those are about the
  address.
- **Attempt counts are kept.** A failed ask after the lift resumes at the
  ladder's NEXT step, not the first.
- **A floor bounds the churn.** Additions repeat without any fault: a LAN
  router announcing new IPv6 prefixes (SLAAC passes the filter, and RFC
  4862's 2-hour floor does not apply to a new prefix), a flapping VPN or
  Wi-Fi, two change sources lagging each other. Allow one lift per peer
  per cadence's first step (30 s per peer, retry_min per relay), measured
  from that peer's previous lift. A relay whose peer the gate still holds
  is skipped. The first fill of an empty address set (an offline start)
  lifts too.
- **Only an addition lifts.** Nothing is lifted on a removal or on a poll
  tick.

**How to apply:** when a component backs off on failure, ask whose fault
the failure records. If the cause can be local (no route, no address),
reset on the local recovery signal, rate-limit the reset per peer, and
prove it with a wire test where the peer comes back inside its backoff
(control: no network view → the peer waits out its backoff). Related:
[[an-untried-address-is-not-held-by-a-backoff-it-did-not-earn]].

*References: an-untried-address-is-not-held-by-a-backoff-it-did-not-earn*

*Observed 2026-10-25 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "domain-a-backoff-exemption-unpaces-every-caller"
description: "A failure class exempted from backoff is a tight loop for every dial source that relies on the gate for its pace (a periodic reconnect round above all); \"never a tight loop\" must be checked per caller, and a log line must state the delay…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 49be94ca098f4a0a
---

## A failure class exempted from backoff is a tight loop for every dial source that relies on the gate for its pace (a periodic reconnect round above all); "never a tight loop" must be checked per caller, and a log line must state the delay that applies to that caller

InterWeave ADR-0011 A 2026-10-09 exempted a circuit dial that failed at its relay hop from the peer backoff,
because nothing was learnt about the destination. It claimed that "a relay that stays down costs the ordinary
cadence, never a tight loop". That was true only of the retry scheduler. Every other dial source was admitted
again at once: DialPeer, a held send's dial, the path race, and above all the composition's discovery round.
That round ticks every second and reconnects every allowed, unconnected peer, and it leaves its pace to the
gate's backoff. A phone measured 357 redials of one peer in 13 minutes. Each line said delay_ms=300000, the
scheduler's delay, which applied to none of them.

architect-cto's DECISION (ADR-0011 A 2026-10-21): the hop failure HOLDS the route (every circuit through that
relay to that peer) for the ordinary cadence, refused to every caller with the hold named. The relay's first
direct connection releases it. The peer's other routes stay admitted.

I guessed the caller twice (relay_reached, then a held send) before reading the dial sources. The client's
agent stating that nothing on its side redials settled it.

**How to apply:** before exempting any failure from backoff, list every dial source and ask which of them
paces itself and which relies on the gate. A reconnect round that "relies on the backoff" is the usual tight
loop. Put the replacement hold at the admission gate, so it binds every caller, and prove it by driving the
periodic round, not only the call you suspect. A log line names the hold that refused the dial, never a
schedule that does not apply to that caller. Related: [[domain-retry-trigger-is-an-edge]],
[[an-untried-address-is-not-held-by-a-backoff-it-did-not-earn]], [[j48-relay-hop-unreached-tight-loop]].

*References: an-untried-address-is-not-held-by-a-backoff-it-did-not-earn, domain-retry-trigger-is-an-edge, j48-relay-hop-unreached-tight-loop*

*Observed 2026-10-22 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "a-refusal-memo-is-invalidated-when-the-predicate-widens"
description: "A memo that suppresses re-offering an address it already offered must be invalidated when the admission predicate that refused it widens; otherwise a start-up ordering race (0.0.0.0 reports 127.0.0.1 before the LAN address) holds a valid…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 135e79a3d0798427
---

## A memo that suppresses re-offering an address it already offered must be invalidated when the admission predicate that refused it widens; otherwise a start-up ordering race (0.0.0.0 reports 127.0.0.1 before the LAN address) holds a valid route for the memo's whole TTL

**Mechanism.** A wildcard (0.0.0.0) libp2p listener reports its
addresses one at a time, and loopback can come before the LAN
address. An admission rule that admits a private candidate only once
the host has a private listener (InterWeave ADR-0052 rule 3) refuses
a cached private route offered in that gap. The discovery memo, which
dedups offers to the address book, recorded the offer as made and did
not repeat it for five minutes: the peer stayed "reconnect refused
class=no_known_address" with no dial. Seen 1 run in 24 with three
pairing test binaries at once; never with one binary at ten threads.

**Rule.** A dedup/suppression memo in front of a gate keys on the
gate's input as well as the item: when the refusing predicate's
boundary widens (a new own listener, a network addition), every
memoed offer is due again. InterWeave's fix (#468, bdc7ac89): the
substrate counts each widening and the memo and Identify's learn site
re-offer when the count moves.

**How to apply:** for any memo, cache or backoff that sits before an
admission check, ask "what makes a refused item admissible later, and
does the memo hear about it?" See also
[[an-untried-address-is-not-held-by-a-backoff-it-did-not-earn]].

*References: an-untried-address-is-not-held-by-a-backoff-it-did-not-earn*

*Observed 2026-10-31 (p2p-network-dev)*

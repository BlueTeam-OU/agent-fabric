---
role: "p2p-network-dev"
class: domain
topic: "libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr"
description: "An address-class predicate that reads only the first /ip4|/ip6 pair is bypassed by stacking a second host behind a public literal; judge the whole multiaddr shape"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - fe48cc8afff3d808
---

## An address-class predicate that reads only the first /ip4|/ip6 pair is bypassed by stacking a second host behind a public literal; judge the whole multiaddr shape

libp2p-tcp 0.45.0 `multiaddr_to_socketaddr` pops from the END of a
multiaddr and connects to the LAST ip/tcp pair, ignoring any prefix.
libp2p-dns 0.45.0 `do_dial` resolves a `dns*`/`dnsaddr` component at
ANY position. So `/ip4/8.8.8.8/tcp/1/ip4/127.0.0.1/tcp/22` reads as
public to a first-pair predicate and connects to loopback, and
`/ip4/8.8.8.8/tcp/4001/dns4/<peer's name>/tcp/80` resolves the peer's
name. Measured on a real socket: `crates/transport/libp2p/tests/
root_funnel.rs` `the_control_tcp_dials_the_last_host_of_a_stacked_address`.

**Why:** every learn-site hook, the root funnel, the DCUtR punch
boundary and the AutoNAT server's dial-back target all read the first
pair, and all were bypassed (InterWeave #111 DNS review P1-1). The same
shape hides in the LISTENER side: a relay reservation address
`<relay-chosen>/p2p/R/p2p-circuit/p2p/me` counted as this node's private
listener.

**How to apply:** an address boundary is an allow-list over the WHOLE
multiaddr (one literal host, first; at most one tcp|udp port; at most
one trailing /p2p), one shared function (`reachability::literal_host`),
applied to candidates and listeners alike. Feed every sibling predicate
the stacked shapes beside the unstacked control.

*Observed 2026-09-25 (p2p-network-dev)*

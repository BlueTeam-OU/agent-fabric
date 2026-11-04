---
role: "p2p-network-dev"
class: domain
topic: "domain-address-class-is-not-reachability"
description: "A private-range address is not LAN-reachable — carrier rmnet /32s on Android are 10.x; only the network's transport type tells them apart"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - c734f8ad6a01e462
---

## A private-range address is not LAN-reachable — carrier rmnet /32s on Android are 10.x; only the network's transport type tells them apart

An address-class floor (private admitted, special-use refused) does not answer "can a reader of this address reach it". On Android, mobile data puts carrier-side private IPv4 /32s on rmnetN (Pixel 9a: A private-network address/32, a private-network address/32 beside wlan0). A 0.0.0.0 listener reports them, so a Show list and Identify's listen_addrs both offer them. A LAN peer can't reach them, so it dials dead addresses, and the carrier-side IPs are disclosed to it.

Two shortcuts that look right but are wrong: "/32 means unreachable" is false, because a WireGuard tun 10.x/32 is reachable by its VPN peers. "Drop everything on cellular" is also false, because cellular global IPv6 is reachable on some carriers. The signal that tells them apart is the platform's per-network transport (NetworkCapabilities TRANSPORT_CELLULAR), and getifaddrs doesn't carry it.

In InterWeave (2026-10-26), the flat `NetworkView` drops the transport type, and ADR-0062 d4 shows "classes the add admits". I asked architect-cto, QUESTION 01a17962, job j76 ([[j76-cellular-addresses-state]]).

*References: j76-cellular-addresses-state*

*Observed 2026-10-26 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "domain-address-class-is-not-reachability"
description: "A private-range address is not LAN-reachable — carrier rmnet /32s on Android are 10.x; only the network's transport type tells them apart, and the OS binds addresses the platform's view never reports"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - b5d43bcf5f0421ec
  - c734f8ad6a01e462
---

## A private-range address is not LAN-reachable — carrier rmnet /32s on Android are 10.x; only the network's transport type tells them apart, and the OS binds addresses the platform's view never reports

An address-class floor (private admitted, special-use refused) does not answer "can a reader of this address reach it". On Android, mobile data puts carrier-side private IPv4 /32s on rmnetN (Pixel 9a: A private-network address/32, a private-network address/32 beside wlan0). A 0.0.0.0 listener reports them, so a Show list and Identify's listen_addrs both offer them. A LAN peer can't reach them, so it dials dead addresses, and the carrier-side IPs are disclosed to it.

Two shortcuts that look right but are wrong: "/32 means unreachable" is false, because a WireGuard tun 10.x/32 is reachable by its VPN peers. "Drop everything on cellular" is also false, because cellular global IPv6 is reachable on some carriers. The signal that tells them apart is the platform's per-network transport (NetworkCapabilities TRANSPORT_CELLULAR), and getifaddrs doesn't carry it.

**The platform's view is narrower than the bind set** (Pixel 9a, API 37, 2026-10-27). Classifying only what the network callback reports still leaked both carrier addresses, because neither network ever reached the callback:
- the INTERNET cellular network kept in the background behind validated Wi-Fi (no FOREGROUND). The platform adds FOREGROUND to an app's listen;
- an IMS/MMTEL network without NOT_RESTRICTED, which an app cannot request at all;
- the phone's own hotspot downstream (wlan1, LOCAL_NETWORK, no INTERNET). It is reported only to an app at targetSdk 37 (platform_compat ENABLE_MATCH_NON_THREAD_LOCAL_NETWORKS). At 36 no listen, even one naming LOCAL_NETWORK, hears it.

The wildcard listener binds all of them anyway. The rule that held on the device: where a platform view is present, a bound private-range address the view does not hold counts as on no local network (not shown, not advertised, not a punch candidate). It stays bound and known, and a view that names it later lifts it. Unknown is then withheld, not offered. The cost is that a network the bridge cannot read (the hosted hotspot) is unshown, and that cost is recorded as a limit.

**Shared address space 100.64.0.0/10 (RFC 6598) is not "never a LAN".** Mesh overlays (WireGuard/Tailscale-style) number their members from it, and InterWeave's own two-host link does. The reason that holds for withholding it from Identify is that the peer-learned floor already refuses it as a candidate, so advertising it serves no one. Such peers meet through an operator-written static entry. A reason that rests on who numbers a range breaks on the first counter-example; give the one that holds whoever numbered it.

**Withholding is not retraction.** A peer that ran Identify before an address was classified keeps the address it learned. Withholding only stops future advertisement.

In InterWeave: ADR-0052 rule 10 (both cases and the shared space), CONNECTIVITY.md §14. State files: [[j76-cellular-addresses-state]], [[j82-rule-10-unviewed-private-state]], [[j84-shared-address-space-state]]. Test shape: [[domain-a-withhold-set-holds-both-orders]].

*References: domain-a-withhold-set-holds-both-orders, j76-cellular-addresses-state, j82-rule-10-unviewed-private-state, j84-shared-address-space-state*

*Observed 2026-10-31 (p2p-network-dev)*

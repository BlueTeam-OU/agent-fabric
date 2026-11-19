---
role: "fabric-coordinator"
class: rationale
topic: "d9-public-port-fabric-h2"
description: "D9 = fabric-h2 InterWeave on public 195.69.140.18; any source, whole range, exposure accepted by owner 11-14 (#597); probe waits on provider"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66021287aed5ee99
---

## D9 = fabric-h2 InterWeave on public 195.69.140.18; any source, whole range, exposure accepted by owner 11-14 (#597); probe waits on provider

The owner, in architect-cto-01's session on 2026-11-13, said "public ip and port was my raccomandation" for D9: fabric-h2 cannot dial back to develop-qzapp. architect-cto relayed it in INFO 01a1d37c-9bcc. My answers are REPLY 01a1d37c-a5a3 and REPLY 01a1d37d-4deb.

What I undertook:
- One amendment of ADR-064 rule 1 and ADR-048. Admission moves from the source address to roster PeerIds. The roster rows on h2 carry the public address. Only the ports of profiles placed on h2 are forwarded, not the whole 47100-47199 range.
- It waits on two things from the owner: the public IP, and an explicit word accepting InterWeave Stage 18's open adversarial gate as a known limit. Ask the owner for both. Do not infer either from the direction.

A public port does not give h2 a send of its own. That needs way (a): develop-qzapp keeps a dialled connection. p2p-network-dev measures idle and redial on one host (architect-cto's REQUEST). I confirm it across hosts in j706 P2's two-host check.

The control plane does not need the way back: in rule 18 the operator dials and the reply rides the same connection.

Related: [[interweave-only-cutover-owner-decisions]], [[h2-owner-answers-2026-11-11]].

**Way (a), measured on loopback by p2p-network-dev-01** (relayed in INFO 01a1d39d-9553): an idle connection stayed open for 180 s, and the side holding the static-bootstrap entry redialled about 1 s after the peer restarted. The side with no address never redials. No InterWeave rule keeps the connection open: a parked gossipsub 0.50.0 stream does. architect-cto recommends making it an InterWeave rule. My cross-host check still has to confirm it past 180 s, on a real link.

**2026-11-13, later:** the owner says the public IP "was already provided" and to "check under proxmox". It is not in my memory, the GZCoord history, the registry, or fabric-h2's own interfaces (ens18 only, a private-network address). I hold no PVE credential, so I sent REQUEST 01a1d3b7-77ff to devex-tooling, the holder of the PVE token, to read it via the API (node network, OPNsense WAN). The Stage 18 word is still to be asked.

**devex-tooling's PVE read, 07:05Z (REPLY 01a1d3b9-9f74), GET only:**
- No public address is visible on any interface or guest the API shows.
- The node's vmbr0 is a private-network address/24 (gw .1, its default route), which is the provider's private network.
- vmbr1, commented "OPNsense WAN", has no address.
- vmbr2, commented "OPNsense LAN", is a private-network address/24.
- OPNsense is not a guest on the node: the only VM is 101.

So the public IP is upstream of s13337, at the provider's NAT, outside the PVE API. Ask the owner for it, or for where the provider's panel shows it.

**Resolved 07:10Z (devex-tooling REPLY 01a1d3be-a648, the owner's word in its session):** OPNsense exists but the provider manages it, outside the PVE token's view. fabric-h2's public address is 195.69.140.18. The provider's OPNsense forwards the InterWeave port from there to a private-network address. The owner asks the provider for the forward, and we touch nothing. Still open: Stage 18 / the network rows on the pinned 0.2.0 release.

2026-11-13 (architect-cto-01 INFO 01a1d6df): the kept connection is an InterWeave rule on main since #657 (c94f6be69), CONNECTIVITY.md §14. One direct connection per allowed data-plane peer is held past the 60 s idle timeout and pinged every 15 s. It is on in every profile. Only the side with a static-bootstrap entry redials: about 1 s after a daemon restart; backoff 30 s → 5 min, not measured. The side with no address never redials. Not yet proved: idle past 180 s on two real hosts, NAT, carrier drop. My two-host check is the first measurement, and its figures go to architect-cto-01. The consumer's record is InterWeave#665 (ADR-0055 d2, d5b).

**2026-11-14, j816 (BlueTeam-OU/agent-fabric#597):** the owner chose any source over the whole range 47100-47199 (provider DNAT 195.69.140.18 → a private-network address, requested 11-13, unconfirmed). In my session the owner explicitly accepted the internet-reachable handshake/parser exposure before the Stage 18 gate closes, so that word is no longer open. #597 amends ADR-064 rule 1 (any-source forward allowed where the coordinator has no fixed address, on the owner's word) and ADR-069 rule 2 + a §1 row, and sets fabric-h2 interweave_address 195.69.140.18 (inert: no roster row names a host). It also contradicts my 11-13 plan to forward "only the profiles' ports". Next: when the provider confirms, send devex-tooling a REQUEST to probe from develop-qzapp with the throwaway account's port. No roster row names fabric-h2 before that.

*References: h2-owner-answers-2026-11-11, interweave-only-cutover-owner-decisions*

*Observed 2026-11-14 (fabric-coordinator)*

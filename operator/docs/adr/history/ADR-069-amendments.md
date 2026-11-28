# ADR-069 — amendment history

### Amendment 2026-11-14 — fabric-h2's InterWeave range is a public forward from any source

Rule 2 said develop-qzapp reached fabric-h2 directly over the LAN and its
VPN. That stays true of ssh (ADR-048). For InterWeave, develop-qzapp is
the owner's laptop and travels, so no source address can be admitted;
on 2026-11-13 the owner asked the provider, who manages the OPNsense in
front of s13337, for a DNAT of 195.69.140.18 TCP 47100-47199 to
192.168.200.79 on the same ports, a WAN rule admitting it from any
source, and a static DHCP lease for the VM (devex-tooling's REQUEST
01a1d3c7-8b7d-718f-bb6e-c77c11fd9f70). ADR-064 rule 1, amended the same
day, allows that shape on the owner's word.

The owner's word, 2026-11-14, in the coordinator's session: the exposure
of InterWeave's handshake and parser to the internet is accepted as a
known limit for fabric-h2, over the whole range rather than one port
first. The question put to the owner named the gate as InterWeave's
Stage 18 adversarial gate; the record cites it as ADR-0034 §7's release
gate, the name this tree gives it. SPIKE-004's deferred limits were not
asked, so the record says they are still open. The forward is a new dependency, so §1 gains its row (rule 1).
No roster row names fabric-h2 until a probe from develop-qzapp reads
the forward back; until then the row's dependency is not relied on. Its
degraded mode is none documented: the relay binds loopback on
develop-qzapp and does not reach a second host (ADR-033 §7).

### Amendment 2026-11-28 — SPIKE-004's limits accepted for fabric-h2's first account

Rule 2 said the 2026-11-14 word did not answer SPIKE-004's deferred
limits for a public listener, and that no roster row names fabric-h2
until a probe from develop-qzapp reads the forward back. ADR-064 rule 1
asks this record to say how those limits are consumed or, on the
owner's word, accepted.

The question put to the owner, 2026-11-28, in the coordinator's session
(j860), named the four limits SPIKE-004's phase-B closing record
(InterWeave `architecture/roadmap/SPIKES.md`, the same text at the
pinned v0.4.0 and on main) carries by name: hole-punch success rates
against the NAT population in the wild, a public VM, a carrier's CGNAT,
and operationally independent relay and probe services. It also named
the fifth that the record leaves open for the owner: interface change
on real hardware.

The question said which of them are live here. fabric-h2 enables no
relay, DCUtR, AutoNAT or Kademlia, and develop-qzapp dials it directly,
so the first, third and fourth are not relied on. A public listener is
live, and so is interface change: develop-qzapp travels, and only it
redials, with backoff from 30 s to 5 min. The two-host check measures
interface change.

The owner chose "Accept, scoped": "All five as known limits for
fabric-h2, only for the throwaway two-host-check account; agents move
later on your word on the parity report." Nothing has consumed any of
the five, because both live checks were TCP connects with no InterWeave
daemon.

The forward was read back by the coordinator from develop-qzapp
(`docs/live-checks/2026-11-27-fabric-h2-public-forward.md`). So was the
VM's firewall admitting the whole range
(`docs/live-checks/2026-11-28-fabric-h2-firewall-admits-the-range.md`).
Both probes left through 2.35.202.83 while the VPN to 192.168.200.0/24
was up, a split tunnel, so the #597 review's hairpin case did not arise.
A dial from inside the provider's LAN is not measured.

InterWeave ADR-0055 decision 5b, whose limits ADR-064 rule 1 accepts for
fabric-h2, covers a private overlay. Its Revisit conditions name "a
second host reached across the open Internet" separately. That record
is InterWeave's, so the point goes to its architect-cto and this record
does not restate it.

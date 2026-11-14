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

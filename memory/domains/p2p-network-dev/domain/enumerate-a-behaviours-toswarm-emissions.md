---
role: "p2p-network-dev"
class: domain
topic: "enumerate-a-behaviours-toswarm-emissions"
description: "Before enabling a libp2p behaviour, grep its ToSwarm emissions — libp2p-mdns 0.49 emits NewExternalAddrOfPeer for every discovered (peer, addr), untrusted; a Dial needs an origin at the gate; an address emission is a door into the address…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e58957877ac601b9
---

## Before enabling a libp2p behaviour, grep its ToSwarm emissions — libp2p-mdns 0.49 emits NewExternalAddrOfPeer for every discovered (peer, addr), untrusted; a Dial needs an origin at the gate; an address emission is a door into the address book

What a behaviour can do to the Swarm is the set of `ToSwarm::` variants
it pushes, and that set — not the README — is what admission must
cover. `grep -rn 'ToSwarm::' <crate>/src` on the pinned version answers
it in one line.

**libp2p-mdns 0.49.0** (behaviour.rs:336-344): for every newly
discovered (peer, address) it pushes
`ToSwarm::NewExternalAddrOfPeer { peer_id, address }` unconditionally,
with no trust check. libp2p-swarm 0.48 forwards it to every behaviour as
`FromSwarm::NewExternalAddrOfPeer` and emits the SwarmEvent. So any
host on the multicast domain can put an address for ANY PeerId into the
Swarm. It emits no `ToSwarm::Dial`, so it originates no dial.
As of that pin no enabled behaviour (kad, gossipsub, identify, autonat,
relay, dcutr) consumed the event — a fact about versions, not an
invariant: a future release that consumes it turns a LAN broadcast into
dialable address-book content with no change in our code.

**What to do with it:** wrap the behaviour and swallow the emission, so
the only route from a discovery packet to a dialable address is the
discovery pipeline's normalization, bounds, dedup and admission; pin it
with a test that no such event leaves the wrapper. InterWeave made it a
rule for every provider (ADR-0011 amendment 2026-09-20, "Discovery never
writes the address book").

**How to apply:** for each behaviour enabled or bumped, list its
`ToSwarm` variants: `Dial` → it needs an admitted origin at the root gate
before construction; `NewExternalAddrOfPeer` / `NewExternalAddrCandidate`
→ an address-provenance door to filter at the wrapper; then list the
`FromSwarm` consumers of each. Re-run on every libp2p bump. Same class
as [[kademlia-routing-table-is-a-second-door]].

*References: kademlia-routing-table-is-a-second-door*

*Observed 2026-10-15 (p2p-network-dev)*

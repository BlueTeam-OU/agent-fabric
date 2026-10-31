---
role: "fabric-coordinator"
class: rationale
topic: "gzcoord-not-on-interweave"
description: "The owner, 2026-10-19: the fleet uses InterWeave as its transport, but GZCoord (protocol, mapping, carrier, tests, docs) never enters the InterWeave repository, which stays a general-purpose transport for people too; GZCoord gets its own…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ff922d89d8da8cb
---

## The owner, 2026-10-19: the fleet uses InterWeave as its transport, but GZCoord (protocol, mapping, carrier, tests, docs) never enters the InterWeave repository, which stays a general-purpose transport for people too; GZCoord gets its own agent-fabric-coord repository

Two answers of the owner on 2026-10-19, read together:
- To me: "GZCoord must not go onto Interweave - they are different things, difefrent layer. If you
  want you can plan to create an agent-fabric-coord repo. well organized, moving there related adr
  and creating contract and moving also the validations."
- To architect-cto-01, relayed verbatim (REPLY 01a1536d): "I want to you to use Interweave as the
  fleet transport but that don't meantha gzcoord should go in the interweave repo. Interweave must
  remain a general purpose transport avaiable also for human to human comunication".

**Why:** GZCoord is the agents' coordination protocol; InterWeave is a general transport. The
fleet rides on InterWeave as one client among many; the protocol is not InterWeave's.

**How to apply:**
- InterWeave's side is generic only: its ADR-0055 (re-cut at 280b70e4, "automated clients are
  first-party consumers above a general-purpose transport") and AUTOMATED-CLIENT.md state what any
  machine client gets and owes; no GZCoord name, rule or test there.
- The GZCoord-over-InterWeave mapping, the carrier, the roster and their records are the fabric's,
  homed in the planned agent-fabric-coord repository (j290 plan first, then the carrier record).
- The transport facts architect-cto-01 measured stand: AcceptedV2 is admission, no durable
  broadcast (ingress 32 burst/120 a minute per peer drops silently), dedup 10,000/5 min in memory,
  queue 256, 48 KiB fixed (compress then chunk), PeerId bound by attestation, ports fail only
  across accounts.
- My first reading ("not onto InterWeave at all") was wrong in half; the owner's dual-write soak
  and login+coordinator-signed roster answers apply to the carrier as designed in the coord repo.

*Observed 2026-10-19 (fabric-coordinator)*

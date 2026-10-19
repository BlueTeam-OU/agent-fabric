---
role: "p2p-network-dev"
class: domain
topic: "a-discovered-circuit-is-a-third-party-assertion"
description: "A /p2p-circuit address is peer-supplied: admit a peer's OWN circuit (from Identify) only if the prefix through /p2p/<relay> meets the address floor, refuse a foreign destination or a nested circuit as its own class; a circuit learned…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 31ed20318e710169
---

## A /p2p-circuit address is peer-supplied: admit a peer's OWN circuit (from Identify) only if the prefix through /p2p/<relay> meets the address floor, refuse a foreign destination or a nested circuit as its own class; a circuit learned through discovery may be a third party's claim, so refuse every circuit there

Two rulings in InterWeave (ADR-0052 rule 8, 2026-09-22 and 2026-09-27):

- **Own circuit, from Identify:** the peer asserts a route to ITSELF through
  a relay. Judge the prefix up to the relay's `/p2p/<relay>` by the class
  floor (or the operator set); after `/p2p-circuit` allow nothing or the
  advertising peer's id; refuse a nested circuit. A different destination is
  a peer asserting a route to someone else — its own refusal class and
  counter. libp2p-relay 0.22's client refuses a circuit without a relay peer
  id, so the book stores `<prefix>/p2p/<relay>/p2p-circuit` and restores the
  destination at dial.
- **From discovery (Kademlia, mDNS, a learn command):** the candidate may
  carry a third party's assertion, so reusing Identify's predicate admits
  routes nobody vouched for. Fail closed: refuse every circuit (class
  `relayed`). Accepted cost: a relay-only peer known only through discovery
  is undialable until Identify gives its circuit.

**How to apply:** pick the predicate by who is asserting, not by the address
shape; when a new learn door reuses an existing predicate, check whose
assertion that predicate was written for. Related:
[[root-gate-prunes-the-extension-not-the-explicit-list]].

*References: root-gate-prunes-the-extension-not-the-explicit-list*

*Observed 2026-10-18 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "domain-failure-class-by-what-not-who"
description: "Operator-facing dial-failure classes split by WHAT was refused (a policy refusal of a dialable route vs a refusal of the route itself), not by WHO refused it (this node vs the library)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - b2ef2607fdb8d621
---

## Operator-facing dial-failure classes split by WHAT was refused (a policy refusal of a dialable route vs a refusal of the route itself), not by WHO refused it (this node vs the library)

InterWeave #281 (observability.md:122, architect-cto's ruling): the first fold sentence said "every refusal
THIS NODE makes before a socket opens → `denied`, every refusal the library makes → `dial_failed`". The
blind review found two refusals this node makes that had always (rightly) been `dial_failed`: an admitted
ticket that is undialable (no peer, not a multiaddr, a circuit under a non-circuit origin) and a circuit on a
node with no relay transport. The rule that holds: a POLICY refusal (this node chose not to dial a dialable
route) is `denied`; a ROUTE refusal (the admission cannot be dialled, whoever says so) is `dial_failed` — it
is permanent, the address leaves the book, and an operator reading `denied` would look for a policy that is
not there.

**How to apply:** when naming a failure class, write the operator's next action for it; two causes with the
same action share a class even if different components raise them. Then enumerate every producer of each
class (grep the error constructors) before stating the rule in prose.

*Observed 2026-10-15 (p2p-network-dev)*

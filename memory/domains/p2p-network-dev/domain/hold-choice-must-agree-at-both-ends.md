---
role: "p2p-network-dev"
class: domain
topic: "hold-choice-must-agree-at-both-ends"
description: "A per-connection keep-alive choice in libp2p must be one both ends make alike — idle close is per end; to_endpoint/is_dialer ignore role_override"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - fbe6d9125df5f6ad
---

## A per-connection keep-alive choice in libp2p must be one both ends make alike — idle close is per end; to_endpoint/is_dialer ignore role_override

libp2p closes an idle connection when EVERY handler at ONE end votes not to keep it, so a rule that keeps "one connection per peer" must pick the same connection at both ends, or each end closes the one only the other held and the pair holds none (#657 review R1, 2026-11-13). Local age (`since_ms`) disagrees for two crossing dials. What both ends read alike: the dialer role with the role override applied — `ConnectedPoint::Dialer { role_override }` → `role_override`, `Listener` → listener. `ConnectedPoint::to_endpoint()` and `is_dialer()` IGNORE the override (libp2p-core 0.43/0.44 `connection.rs:115-125`), so a DCUtR punch reads as dialer at both ends through them. Order by "dialled by the lower peer id" first.

Also from #657: the ping crate's handler reports `Unsupported` once and goes `Inactive` for good, so a refusal kept under one rule must be remembered by the behaviour if a later role (control peer) treats a refusal differently.

Also: a two-daemon fixture that starts the dialler first sends a dial to a host not yet listening, and the 30 s peer backoff outlasts a 30 s test patience — start the listener first.

Related: [[j165-data-plane-hold-handover]].

*References: j165-data-plane-hold-handover*

*Observed 2026-11-13 (p2p-network-dev)*

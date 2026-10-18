---
role: "p2p-network-dev"
class: domain
topic: "domain-silence-bound-arms-on-first-ping"
description: "A client-side liveness timer must arm on evidence the server runs keepalive (the first ping read), not at connect, when the handshake does not say whether keepalive was granted"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 90d5ef51afb69e36
---

## A client-side liveness timer must arm on evidence the server runs keepalive (the first ping read), not at connect, when the handshake does not say whether keepalive was granted

A client that always OFFERS keepalive and a server that runs it only when its config enables it, with a
hello response that does not echo the granted features, means the client cannot know pings will come. A
fixed "no frame read for N s → Timeout" timer then kills every healthy idle connection to a server with
keepalive off. Arm the bound at the first ping READ; before that only the caller's own timeout and OS
liveness bound the wait.

A second half, about landing order: the client's bound is only safe when the server's configured
interval + response_timeout sits inside it. So the config validation that keeps the server inside the bound
lands BEFORE (or with) the client's timer, never after. InterWeave #230 (timer) waited for #228 (profile
bound, 120 s) for exactly this reason.

**How to apply:** for any one-sided timeout over an optional, negotiated feature: (1) does the wire tell
this side the feature is on? if not, arm on first evidence; (2) which config on the other side must stay
inside the bound, and is its validation already on main?

*Observed 2026-10-15 (p2p-network-dev)*

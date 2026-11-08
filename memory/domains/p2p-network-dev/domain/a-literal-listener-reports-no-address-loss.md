---
role: "p2p-network-dev"
class: domain
topic: "a-literal-listener-reports-no-address-loss"
description: A libp2p TCP listener bound to one IP literal gives no signal when that address or its link goes (only a wildcard listener watches interfaces); established connections survive the deletion, so a daemon with no platform view must listen on…
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 093b897548f107d7
---

## A libp2p TCP listener bound to one IP literal gives no signal when that address or its link goes (only a wildcard listener watches interfaces); established connections survive the deletion, so a daemon with no platform view must listen on a wildcard to see a lost link

**Field fact.** libp2p-tcp runs its interface watcher (if-watch) only
for a listener on an unspecified IP (0.0.0.0 / ::). A listener on a
literal reports no change when its address leaves the host, and the
kernel does not close established TCP connections when the address
or link is deleted: they just stall until a keepalive or an
application timeout ends them. A stack whose network-change
detection is fed by the listeners' bound set therefore never sees
the loss.

**Measured** (InterWeave, 2026-10-27, two network namespaces over a
100.64.0.0/30 link): wildcard listeners closed at both ends within
10 s of deleting the link and redialled when it returned; literal
listeners kept "connected" past that window. Mutating the detector's
close to false failed the wildcard case at the same assertion (the
close is the detector's). architect-cto then ruled the deployment
shape wildcard-only (ADR-0055 5b), matching the embedded-android
profile's wildcard-only rule (CONNECTIVITY.md 14).

**How to apply:** when a deployment, a profile schema or a test
chooses a listen address, treat "a literal or a wildcard" as not
equivalent: a literal needs some other source of address-loss truth
(a platform view, keepalive bound) or it shows a dead link as
connected. Pin the choice with a case that runs both shapes, the
wildcard as positive control.

*Observed 2026-10-31 (p2p-network-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "nat-trials-need-a-fresh-port-each"
description: "Router or host conntrack state outlives a hole-punch trial, so trials that reuse one listen port contaminate each other (eim punch 2/10 shared port vs 10/10 port-per-trial); give each trial a fresh port and hold every other variable fixed…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b3ca71b2854a31d6
---

## Router or host conntrack state outlives a hole-punch trial, so trials that reuse one listen port contaminate each other (eim punch 2/10 shared port vs 10/10 port-per-trial); give each trial a fresh port and hold every other variable fixed before naming a cause

SPIKE-004 phase B (2026-09-26, podman NAT routers): "endpoint-independent
mapping mostly fails, 2 of 10" was the harness. Every trial reused port 4001;
the routers' connection tracking from earlier trials still held the mapping,
so from trial two the router behaved endpoint-dependently. Port per trial:
eim 10 of 10, eds 0 of 10; control on the shared port: 1 of 10. The final
review then found router A's public interface (eth1 vs eth0) also tracked
the result, so the cause was narrowed to "likely, not isolated" and the
correction re-sent before it could reach the verdict.

Same mechanism class as [[j23-same-port-hang-is-conntrack]]: stateful
tracking keyed on a reused port tuple outlives the connection that made it.

**How to apply:** in any NAT, punch or restart harness, allocate a fresh
port per trial (or flush tracking between trials, which needs root); when a
re-run differs from the first in more than one variable, report the cause as
likely and name the control that would isolate it; withdraw a wrong number to
everyone who received it, at once, saying which other findings stand.

*References: j23-same-port-hang-is-conntrack*

*Observed 2026-10-18 (p2p-network-dev)*

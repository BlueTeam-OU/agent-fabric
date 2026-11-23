---
role: "edge-hosting"
class: domain
topic: "cloudflare-52x-wildcard-fallthrough"
description: "A steady Cloudflare 521/522 on a hostname with no record of its own is the zone wildcard falling through to another origin, not an outage or propagation; read the exact name's DNS before blaming the Worker"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a48bc4c2c2a831cd
---

## A steady Cloudflare 521/522 on a hostname with no record of its own is the zone wildcard falling through to another origin, not an outage or propagation; read the exact name's DNS before blaming the Worker

In a Cloudflare zone with a proxied wildcard record (`*.zone`), a hostname has an answer even when nothing attached it. This holds before a Worker custom domain is ever attached, and again after one is detached. The request goes through the wildcard to the wildcard's target, and that target's refusal is what the visitor sees:
- **521.** The wildcard leads to an origin that refuses the host.
- **522.** The wildcard leads to a Pages project or origin that doesn't hold the hostname.

So "detach the custom domain" doesn't give NXDOMAIN or a clean error. It gives whatever the wildcard's target answers, and that target may belong to someone else.

**Diagnosis order** for a steady 52x on a Worker hostname:
1. Look up that exact name's own record through the API, and the wildcard.
2. Check the Worker's custom domains and routes.
3. Only then check the Worker itself.

**Why:** in October 2026, one hostname answered 522 because it had no record of its own. The wildcard chained to a Pages project that didn't hold the name. The Worker was healthy on its other hostname. A sibling hostname answered 521 right after its custom domain was detached. These two are independent observations from two zones.

**How to apply:** this differs from the transient 522/523 just after a first attach, which the field slice "Cloudflare 521 vs 522/523" covers. A 52x that persists past that window, on a name with no record of its own, points at the wildcard. In a pause's change record, name the wildcard's answer as the expected visitor effect. Related: [[cloudflare-worker-has-no-pause]], [[gzapp-status-hostnames-2026-10-19]].

*References: cloudflare-worker-has-no-pause, gzapp-status-hostnames-2026-10-19*

*Observed 2026-10-30 (edge-hosting)*

---
role: "domain-transit"
class: domain
topic: "independent-tracers-share-no-cut"
description: "A cross-check tracer that copies the first tracer's largest-component cut agrees by construction near road islands"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - b6dbd492ddc080bb
---

## A cross-check tracer that copies the first tracer's largest-component cut agrees by construction near road islands

A second tracer is independent only if it shares no silent preprocessing with the first. OSMnx's `graph_from_xml` defaults to `retain_all=False` (largest weakly connected component), the same cut `road_graph._largest_component` makes. With both cutting, a stop beside a road island re-snaps onto the main network in both, and they "agree" for that reason alone. The cross-check now keeps every component (`retain_all=True`), so a leg off an island comes out `no_path` (gzapi-org/gzapp#1053, 12fc25d0a).

On 0.5.2-seed it changed nothing: 53 components, 52 small ones with 322 nodes, no stop nearest to one of them. Latent, not measured harm.

**Why:** found by a retired automated reviewer's comment, which I had to judge, not write off. My own review rounds never asked which defaults the two tracers share.
**How to apply:** when building a cross-check, list every default of the second method (component cut, simplification, snap radius, filter) beside the first's, and make each shared one a stated choice. A fixture named "detached" must be checked for detachment. Related: [[node-snap-loops-on-the-wrong-carriageway]].

*References: node-snap-loops-on-the-wrong-carriageway*

*Observed 2026-10-08 (domain-transit)*

---
role: "domain-transit"
class: domain
topic: "monotonicity-by-moving-floor-cascades"
description: "enforce ordering along a line with an anchor from the construction, never by carrying the previous result forward as the next search's floor"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - a75f3a877199abdc
---

## enforce ordering along a line with an anchor from the construction, never by carrying the previous result forward as the next search's floor

When projecting an ordered sequence of points onto a polyline (stops onto
a shape, fixes onto a route), the output must usually be **monotonic** in
sequence order. The obvious implementation — start each search where the
previous one ended — is wrong and fails catastrophically.

**Why:** the floor moves with the result, so one bad projection truncates
the search for every point after it, and the error compounds. Measured
2026-09-20 on the [redacted] road graph, stop-to-carriageway offset:

| rule | median | p90 | >60 m |
|---|---|---|---|
| forward-only moving floor | 12.4 m | **2976.8 m** | 280/786 |
| unconstrained nearest | 8.3 m | 19.1 m | 12/786 |
| **anchored window** | 8.3 m | 19.4 m | 12/786 |

**How to apply:** anchor the search window to something produced by the
CONSTRUCTION, not by the previous answer. Here the tracer records where
each stop's leg ends as it lays the line down, and each stop is projected
within its own two legs — an anchor that cannot drift. Then enforce
ordering as a **clamp** against the previous value, not as a constraint
on the search: the point still finds its true nearest position, and only
the reported chainage is held.

**The test trap:** on tidy synthetic geometry the defect does not show as
an offset explosion — it shows as two DISTINCT points collapsing onto one
chainage. A test asserting only offsets passes on the bug. Assert that
distinct inputs get distinct outputs.

Also: a stub fixture and a lattice were both too well-behaved to catch
this. Exercise the real data source before believing a geometry change —
see [[invariance-beats-a-threshold-test]] and
[[i-stop-checking-when-the-answer-pleases-me]].

*References: i-stop-checking-when-the-answer-pleases-me, invariance-beats-a-threshold-test*

*Observed 2026-09-20 (domain-transit)*

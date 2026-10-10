---
role: "domain-transit"
class: domain
topic: "country-graph-fits-in-the-otp-cap"
description: "measured OTP 2.10 memory for a [redacted]-wide graph vs the [redacted] city graph — the country graph fits the 2 GB container cap"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - fe6eefdc74e1ac45
---

## measured OTP 2.10 memory for a [redacted]-wide graph vs the [redacted] city graph — the country graph fits the 2 GB container cap

Measured 2026-09-27 on develop-qzapp. Both graphs carry the 0.5.x [redacted]
bundle. Same script each time: container start, 20 s idle, then 4 transit
plans and 2 walk plans.

| graph | on disk | startup | idle | after queries |
|---|---|---|---|---|
| city (osm-city clip), 8 GB limit | 10.4 MB | 5.8 s | 315 MB | 563 MB |
| country ([redacted] 2026-09-19 + city), 8 GB limit | 98.5 MB | 13.7 s | 1.14 GB | 1.26 GB |
| country, the normal 2 GB cap | 98.5 MB | 9.2 s | 1.04 GB | 1.08 GB |

The country graph routes walks in Tbilisi and Batumi. Transit plan times
are 0.2–3 s on both graphs, comparable, because the only transit is
[redacted]'s. Before measuring I had estimated "several GB, over the cap".
That was wrong by about 3x.

**Why:** the question "what limits country-wide routing" came up
(2026-09-27). Memory is not the limit: the country graph fits the
per-clone 2 GB cap at about 2x the city graph. The limits are ADR-068's
per-city-engine design and the absence of any non-[redacted] transit
data.

**How to apply:** answer country-wide routing questions with these
numbers, and re-measure if a second city's GTFS joins the graph (transit
data, not streets, then drives memory).
Related: [[otp-builds-from-every-extract-in-its-dir]], [[i-reported-an-inference-as-a-measurement]]

*References: i-reported-an-inference-as-a-measurement, otp-builds-from-every-extract-in-its-dir*

*Observed 2026-09-27 (domain-transit)*

---
role: "domain-transit"
class: domain
topic: "otp-pickup-type-3-is-boardable"
description: "OTP 2.10 non-flex boards a pickup_type 3 stop exactly as 0; type 1 removes it and silently walks the rider to a neighbour"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 48eb7783540196fc
---

## OTP 2.10 non-flex boards a pickup_type 3 stop exactly as 0; type 1 removes it and silently walks the rider to a neighbour

Measured 2026-09-16 on OTP 2.10.0 (the pinned image), three graphs from
three bundles differing only in `stop_times.txt`, frequency-based
scheduled trips with no GTFS-Flex constructs and `FlexRouting` listed
under "Features turned off".

- `pickup_type` / `drop_off_type` **3** (COORDINATE_WITH_DRIVER):
  the stop stays **boardable and alightable exactly as 0**. Itineraries
  byte-identical to the unmodified bundle, zero extra walk.
- **1** (no pickup / no drop-off): the stop is removed and the planner
  **walks the rider to the neighbour** — 552 m in one measured case —
  without failing. A silent relocation, not an error.
- The type-1 bundle is what proves the column is read at all. Without
  that control, "3 changed nothing" is indistinguishable from "the
  column was ignored".

**I expected the opposite** and said so before the run: that OTP2 boards
only `SCHEDULED` in non-flex routing and that 3 would drop the stop.
That reasoning — the `PickDrop` enum, flex being a separate feature —
sounds right and is wrong for 2.10 on a non-flex bundle. Do not
re-derive it from the enum; the behaviour is the fact.

**Consequence for a design:** type 3 is a pure marker to the router. It
can carry an "on request" fact without costing a single itinerary, but
it cannot itself make a stop unsearchable — whatever consumes the
column has to do that. Conversely, never reach for type 1 to express
"do not show this stop": it silently moves riders.

**Caveat on how it was shown.** OTP's GraphQL stoptimes/trip views
return nothing for frequency-based trips, so the mapping is
demonstrated by behaviour (type 3 vs type 1) and not by reading a
`pickupType` field back. A version bump should re-measure rather than
assume.

Related: [[gtfs-seed-drops-name-variants]].

*References: gtfs-seed-drops-name-variants*

*Observed 2026-09-16 (domain-transit)*

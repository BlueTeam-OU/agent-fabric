---
role: "domain-transit"
class: domain
topic: "a-route-number-is-not-a-service"
description: in a scraped route catalogue a number shared by a minibus and a trolleybus is two different services, and no trolleybus route has a published schedule at all
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 8f65bbd48db04610
---

## in the [redacted] source a number shared by a minibus and a trolleybus is two different services, and no trolleybus route has a published schedule at all

**A route number identifies a number, not a service.** In the wikiroutes
catalogue, route 1 is a minibus running 05:30–22:00 every 10 min *and* a
trolleybus with no published schedule. Joining schedules to routes by
number silently merges them.

**No trolleybus route has a schedule anywhere in the source.** Measured
2026-09-17 on both cached files: minibus 42/43 records carry a window,
bus 14/14, **trolleybus 0/10** — ten routes numbered 1–10, not one with a
start, end or headway. That is what a closed system looks like in a
directory nobody cleaned up; it is also what a bad scrape looks like, and
the two are not distinguishable from the data.

**The builder's default fabricated one for them.** Five trolleybus lines
(`route_type` 11: routes 2, 6, 7, 8, 9) shipped in `gtfs.zip` with
06:00–21:00 every 20 min — a window no source states. Under ADR-058
§2.11's "service resumes at", that becomes a confident sentence about a
service nobody has seen run.

**The rule** (architect-cto, 2026-09-17, ADR-035 §2.3): a window is never
borrowed across modes; a route whose source publishes no start, end or
headway gets **no frequency row and no trips** and is named in the build
report as "no published schedule". A default window is a fabrication.

**How to apply:** when joining a timetable to a route, join on
(number, mode) and never on number alone. Before "recovering" a missing
value from a sibling record, check what distinguishes the two records —
the sibling may be a different service, and filling the gap invents data
rather than restoring it. I proposed exactly that fix and it was approved;
measuring the seven affected records before writing the code is the only
reason it did not ship.

Related: [[acceptance-test-is-a-diff-not-a-count]], [[gtfs-version-pins-and-what-ships]].

*References: acceptance-test-is-a-diff-not-a-count, gtfs-version-pins-and-what-ships*

## in a scraped route catalogue a number shared by a minibus and a trolleybus is two different services, and no trolleybus route has a published schedule at all

**A route number identifies a number, not a service.** In the wikiroutes
catalogue, route 1 is a minibus running 05:30–22:00 every 10 min *and* a
trolleybus with no published schedule. Joining schedules to routes by
number silently merges them.

**No trolleybus route has a schedule anywhere in the source.** Measured
2026-09-17 on both cached files: minibus 42/43 records carry a window,
bus 14/14, **trolleybus 0/10** — ten routes numbered 1–10, not one with a
start, end or headway. That is what a closed system looks like in a
directory nobody cleaned up; it is also what a bad scrape looks like, and
the two are not distinguishable from the data.

**The builder's default fabricated one for them.** Five trolleybus lines
(`route_type` 11: routes 2, 6, 7, 8, 9) shipped in `gtfs.zip` with
06:00–21:00 every 20 min — a window no source states. Under ADR-058
§2.11's "service resumes at", that becomes a confident sentence about a
service nobody has seen run.

**The rule** (architect-cto, 2026-09-17, ADR-035 §2.3): a window is never
borrowed across modes; a route whose source publishes no start, end or
headway gets **no frequency row and no trips** and is named in the build
report as "no published schedule". A default window is a fabrication.

**How to apply:** when joining a timetable to a route, join on
(number, mode) and never on number alone. Before "recovering" a missing
value from a sibling record, check what distinguishes the two records —
the sibling may be a different service, and filling the gap invents data
rather than restoring it. I proposed exactly that fix and it was approved;
measuring the seven affected records before writing the code is the only
reason it did not ship.

Related: [[acceptance-test-is-a-diff-not-a-count]], [[gtfs-version-pins-and-what-ships]].

*References: acceptance-test-is-a-diff-not-a-count, gtfs-version-pins-and-what-ships*

*Observed 2026-09-18 (domain-transit)*

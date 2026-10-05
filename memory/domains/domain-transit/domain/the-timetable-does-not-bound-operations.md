---
role: "domain-transit"
class: domain
topic: "the-timetable-does-not-bound-operations"
description: the schedule answers what the service PLANS, never what a vehicle or a shift actually does — those are bounded by driver behaviour, not by a published window
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - ce0c56b19185f126
---

## the schedule answers what the service PLANS, never what a vehicle or a shift actually does — those are bounded by driver behaviour, not by a published window

When a question is about **when a vehicle or a shift exists**, the
schedule is the wrong instrument, however authoritative it looks. It
states the planned service; the thing being asked about is a driver's
behaviour.

**Why:** in an informal network the vehicle exists while a driver runs
the app (ADR-000/001/002), and nothing closes a shift because the last
departure has gone. gzapp's ADR-043 gives operators **force-close for a
stuck shift** — a capability that exists because shifts get stuck — with
no auto-close and no maximum duration. So an open shift is unbounded in
time, and a question like "can a shift cross midnight?" is not answered
by the operating window at all.

**Measured 2026-09-21** on `tools/gtfs_kutaisi/data/wikiroutes_schedules.json`:
56 of 73 routes carry a window; latest end anywhere **23:00** (3 routes),
earliest start 05:30, and **zero** windows where end <= start. So the
published day never crosses midnight — and the correct answer to the
shift question was still "it happens, rarely", because a 23:00 route
plus an app closed at 00:20 crosses, and a stuck shift can be days old.

**How to apply:** when asked a "when does X run / how long has X been
running" question, ask first whether X is a *service* (schedule answers
it) or a *vehicle/shift/driver* (it does not). Give the schedule
measurement AND the reason it does not settle the question. The cache
also says of itself "Schedule seed values; licensing differs from OSM —
verify before production use", so it is a seed even for the service
question.

This has now been the wrong instrument twice: once behind journey
planning, once behind the driver's shift line.

Related: [[a-route-number-is-not-a-service]],
[[gtfs-version-pins-and-what-ships]].

*References: a-route-number-is-not-a-service, gtfs-version-pins-and-what-ships*

*Observed 2026-09-21 (domain-transit)*

---
role: "domain-transit"
class: domain
topic: "a-planar-corridor-cannot-see-a-bridge"
description: "Projecting a no-stop restriction by a 2D corridor restricts lines passing over/under the structure; broad scope with no contact is not a failure"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - e7358486260dee71
---

## Projecting a no-stop restriction by a 2D corridor restricts lines passing over/under the structure; broad scope with no contact is not a failure

A restriction compiled by "shape vertex within N m of the restriction line" (RestrictionCompiler, 25 m, at 53537376a) cannot tell a line ON a structure from one crossing it at another level or meeting its head. On the [redacted] extract, at least 21 shapes cross over a 9 m service-road tunnel (OSM way 1185678889) and each gets a zero-length interval. r-111 direction 0 passes the Red Bridge head on the cross street (79 degrees, 14 m) and gets one too. The test that separates them is heading agreement or overlap length, not distance alone.

Second: under a broad scope (city, or operator while it is unresolved), zero intervals usually means no line uses that road (the Zarati Bridge is 4.2 km from any shape), which is does-not-apply. Only route scope's zero is a real "should apply but failed". Classed as Failed, one such hazard blocks every future import of the city. Fixtures with every case: develop-qzapp/domain-transit/for/backend-dev-02/stop-restriction-fixtures (fd2095555); OBSERVATION 01a12495-9bc6-70e2-8bfd-2dfe5341cc6b; architect-cto ruled the domain reading right and is amending ADR-067 §2.7 (DECISION 01a12496-f3e0, 2026-10-10): under city or operator scope, a geometry clear of every in-scope shape by the projection margin (an ADR-063 calibration value) does not apply; Failed means a near shape yields nothing, or route scope.

**Why:** the compiler's author read ADR-067 §2.7 literally; the domain reading differs, and an over-strict fail-closed rule turns a safety catalogue into an import blocker.
**How to apply:** when restriction geometry meets shapes, classify by heading and level (bridge/tunnel layer) as well as distance; judge "failed" per scope kind. Related: [[node-snap-loops-on-the-wrong-carriageway]], [[independent-tracers-share-no-cut]].

*References: independent-tracers-share-no-cut, node-snap-loops-on-the-wrong-carriageway*

*Observed 2026-10-10 (domain-transit)*

---
role: "fabric-coordinator"
class: domain
topic: "tool-graphhopper"
description: "graphhopper/graphhopper (Apache-2.0 Java routing engine): reviewed 2026-11-08 at the owner's ask for domain-transit — a map-matching and road-graph sidecar beside OTP, not an OTP replacement"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3c28d7cc8e4416da
---

## graphhopper/graphhopper (Apache-2.0 Java routing engine): reviewed 2026-11-08 at the owner's ask for domain-transit — a map-matching and road-graph sidecar beside OTP, not an OTP replacement

Reviewed 2026-11-08 at the owner's request, from github.com/<owner>/graphhopper at HEAD 385b8eda (2026-11-06), for domain-transit (gzapp, [redacted]-shop-transit). Checked against the clone: LICENSE.txt Apache-2.0, pom 12.0-SNAPSHOT (unreleased; last release 11.0, 2025-10-14), needs Java ≥ 25, Maven, Dropwizard server (`java -jar graphhopper-web-*.jar import|server|match config.yml`, port 8989).

- **Open:** /route, /match (map matching with an HMM/Viterbi, GPX in), /isochrone, /isochrone-pt, /spt, /nearest, /route-pt (GTFS reader with frequencies.txt, transfers.txt, GTFS-RT polling, and walking legs only), /mvt debug tiles. Profiles are JSON custom models with flexible, LM or CH modes; a changed profile or GTFS needs a re-import.
- **Not open:** the Matrix API, which is a hosted product only. There is no official Docker image (README points to a community image, israelhikingmap/graphhopper).
- **Network calls:** no telemetry. Elevation (SRTM) downloads happen only when `graph.elevation.provider` is set, and config-example.yml sets it, so clear it for an offline run. GTFS-RT URLs are polled when configured. The Maps UI calls the hosted API only when keys are set.
- **Fit for gzapp:** use it as a sidecar. Map-match driver-phone traces to OSM road paths for shapes.txt (the output is a road path, so it needs a step to turn it into a GTFS shape), and it could replace the stdlib A* in gzapp's tools/gtfs_kutaisi road_graph.py. Use foot routing and isochrones for access legs. Its PT routing is narrower than OTP and, like OTP, assumes a timetable, which marshrutka does not have.

**Why:** domain-transit owns the routing engine and road-graph and shape work. The adoption decision is theirs, with architect-cto (project truth), not mine.
**How to apply:** the sharing went to domain-transit by GZCoord (job j665). If they adopt it, pin a released tag, not a SNAPSHOT. Related: [[external-tools-evaluated]].

*References: external-tools-evaluated*

*Observed 2026-11-08 (fabric-coordinator)*

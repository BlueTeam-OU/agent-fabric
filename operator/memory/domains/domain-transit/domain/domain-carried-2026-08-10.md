---
role: "domain-transit"
class: domain
description: "Overpass API vs. Geofabrik extracts: different freshness and metadata tradeoffs"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 3473255dbe9e00e8
  - 7bb41f8f5646024e
---

## Overpass API vs. Geofabrik extracts: different freshness and metadata tradeoffs

> Learned outside this system; it describes the field, not our implementation.

Overpass API queries the live OpenStreetMap database and returns only the elements matching a spatial/tag query, including full editorial metadata (changeset id, user, timestamp, version) and historical ('attic') queries via `[date:...]`. Geofabrik-style extracts are periodic (typically daily) bulk snapshots covering a fixed geographic region as PBF/shapefile downloads, and normally strip authorship/versioning metadata. Overpass suits a targeted, freshness- or provenance-sensitive query against a handful of elements; a bulk regional extract suits importing a full region for downstream processing such as a geocoder or routing-graph build.

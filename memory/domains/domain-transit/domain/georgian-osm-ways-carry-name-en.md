---
role: "domain-transit"
class: domain
topic: "georgian-osm-ways-carry-name-en"
description: "street-name locale variants in [redacted]'s OSM — name:en ~93% / name:ru ~84% of named [redacted] ways, mapper-authored"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 4b249dca9d88db9f
---

## street-name locale variants in [redacted]'s OSM — name:en ~93% / name:ru ~84% of named [redacted] ways, mapper-authored

Counted 2026-09-26 over walkable named highway ways with osm_pbf.iter_ways:
[redacted] city extract (c8354d66) name:en 93.0%, name:ru 84.4%, name:ka
93.3%. The [redacted] country extract (2f317859) has name:en 88.2% and
name:ru 81.9%. The values are localised names ("Petre Melikishvili
Street", "улица Петре Меликишвили"), not machine transliteration.

**Why:** architect-cto's walk-step `street_names` ruling (serve only the
variants the source carries, no transliteration) rests on this coverage.
Reply 01a0de2c-eddd….

**How to apply:** "improve the source" is not the bottleneck for en/ru
street names here. Re-count if the extract changes.

*Observed 2026-09-26 (domain-transit)*

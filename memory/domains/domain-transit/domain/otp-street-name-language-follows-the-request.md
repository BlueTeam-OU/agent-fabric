---
role: "domain-transit"
class: domain
topic: "otp-street-name-language-follows-the-request"
description: "OTP 2.10 walk-step streetName language — planConnection without locale gives OSM `name`, legacy `plan` gives name:en, a locale picks name:<lang>; underpass is a bogus name"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 4baafdc5a8a6fc21
---

## OTP 2.10 walk-step streetName language — planConnection without locale gives OSM `name`, legacy `plan` gives name:en, a locale picks name:<lang>; underpass is a bogus name

Measured 2026-09-26 on the published graph (otp-graph 0a82e21f, which covers
[redacted] only: Tbilisi returns OUTSIDE_BOUNDS):
- planConnection with no locale returns OSM `name` (Georgian).
- The legacy `plan` query with no locale returns name:en.
- `locale: "ka"` / `"ru"` returns name:ka / name:ru. These can differ
  from `name`; one way's name:ka carries ქეჩა where `name` has ქუჩა.
- An underpass walk is one ordinary step, streetName "underpass" with
  bogusName true. There is no underpass manoeuvre.

**Why:** architect-cto made this a rule in ADR-058 §2.6 (#950): the plan
query sends no locale, and a search profile carrying the key is
refused. Before that, a profile could silently switch street_name.

**How to apply:** query the engine with the backend's own
planConnection shape before asserting what the wire serves. The two
GraphQL entry points differ in their defaults.

*Observed 2026-09-26 (domain-transit)*

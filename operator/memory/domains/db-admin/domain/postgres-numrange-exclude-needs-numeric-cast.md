---
role: "db-admin"
class: domain
description: "EXCLUDE USING gist with numrange() over double-precision columns fails unless both bounds are cast to numeric"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 23b4748be7433114
  - 401f7b3c12fe2ccf
  - f3e2821e744a384e
---

## EXCLUDE USING gist with numrange() over double-precision columns fails unless both bounds are cast to numeric

numrange() only accepts `numeric` arguments; passing `double precision` (float8) values fails at DDL time with `function numrange(double precision, double precision) does not exist`, because float8-to-numeric is an assignment cast in Postgres, not an implicit one that participates in function-overload resolution. This aborts the whole migration on apply rather than causing a silent runtime issue, so it's caught immediately by psql — but it stops every environment cold at that migration until fixed. The fix is explicit `::numeric` casts on both range bounds, e.g. `numrange((col - half)::numeric, (col + half)::numeric)`. Any EXCLUDE constraint or range-typed expression built over double-precision measurement columns (distances in meters, etc.) needs this cast; verified against postgres:16-alpine with a GIST exclusion constraint that then correctly rejected overlapping intervals.

---
role: "db-admin"
class: domain
topic: "pg18-not-null-is-a-pg-constraint-row"
description: "Counting or listing a table's constraints from pg_constraint on Postgres 18 — NOT NULL is a row there too (contype 'n'), and LIKE's '_' is a wildcard; filter by contype and assert the exact set"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 47e65af7754d205e
---

## Counting or listing a table's constraints from pg_constraint on Postgres 18 — NOT NULL is a row there too (contype 'n'), and LIKE's '_' is a wildcard; filter by contype and assert the exact set

Postgres 18 records each NOT NULL in pg_constraint, as contype 'n' with
an auto-generated name such as `<table>_<column>_not_null`. A
catalogue assertion written for earlier majors, like
`count(*) WHERE conname LIKE 'stop_demands_ideal_%'`, then counts more
than the CHECKs. In 0025 (j39, 2026-10-25, commit da5a00791) it
returned 5 against the expected 3. `_` in LIKE matches any single
character, which widens the match further.

**How to apply:** filter on `contype = 'c'` (or the type you mean),
escape `_` as `\_` in LIKE, and assert the exact ordered set of names,
not a count ([[an-empty-set-assertion-is-the-weakest-test]]). A
column's NOT NULL is still checked via `pg_attribute.attnotnull`.

*References: an-empty-set-assertion-is-the-weakest-test*

*Observed 2026-10-25 (db-admin)*

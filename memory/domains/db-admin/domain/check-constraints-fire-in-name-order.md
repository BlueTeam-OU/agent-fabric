---
role: "db-admin"
class: domain
topic: "check-constraints-fire-in-name-order"
description: "A test asserting WHICH CHECK refused a row must make the row violate only that one — Postgres evaluates a row's CHECKs alphabetically by name and reports the first."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 5232d0ecc8aaf230
---

## A test asserting WHICH CHECK refused a row must make the row violate only that one — Postgres evaluates a row's CHECKs alphabetically by name and reports the first.

Postgres checks a row's CHECK constraints in alphabetical order by constraint name and
reports the first one that fails. So a test asserting `error.ConstraintName` passes only
if the bad row breaks that constraint alone. On 0008 (`tile_publications`, 9293fd99c) a
bad vintage also broke `*_pack_url_carries_vintage`, which sorts before `*_vintage_shape`,
so the wrong name would have been reported.

**Why:** cross-column CHECKs, like "the URL contains the vintage", mean one bad value can
break several constraints. Which name you see then depends on alphabetical order, not on
what the test meant to probe.

**How to apply:** when a fixture value feeds more than one CHECK, change every dependent
column with it (here, the URLs carry the bad vintage too) and say so in a comment. Put
cross-column CHECKs at table level: the docs say a column CHECK should reference only its
own column. Related: [[verify-the-mutation-fired]] (cutting a column CHECK can also eat
its comma, and the result is all-red).

*References: verify-the-mutation-fired*

*Observed 2026-10-08 (db-admin)*

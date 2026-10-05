---
role: "db-admin"
class: domain
topic: "postgres18-skip-scan-changes-index-necessity"
description: "PostgreSQL 18 skip-scans a non-leading index column, so a predicate that needs an index on 16 may already be served on 18"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 970dbfd648338a4f
---

## PostgreSQL 18 skip-scans a non-leading index column, so a predicate that needs an index on 16 may already be served on 18

PostgreSQL 18 can use a btree index for a predicate that constrains only
a NON-leading column, probing once per distinct value of the leading
column (a "skip scan", visible as a high `Index Searches` count in
`EXPLAIN ANALYZE`). This breaks the pre-18 rule of thumb that a predicate
not including the index's first column cannot use that index at all. That
rule still holds on 16 and 17, so a probe run against the wrong major
version produces a confidently wrong answer about whether an index is
needed.

Measured 2026-09-09 on `operator_driver_membership`, which carries a
partial unique index on `(operator_id, owner_driver_id) WHERE
status='active'`. The ADR-028 severance sweep filters on
`owner_driver_id` alone. On 400k rows across 40 operators, PG18 chose
that index anyway: 41 index searches, 166 buffers. The cost tracks the
operator count, not the row count, so it degrades slowly.

Two consequences worth carrying:

- Skip scan is a real plan, not a good one. It beats a seq scan and loses
  badly to a seek. Treat it as "the predicate is survivable", never as
  "the index review is finished". It is acceptable where the skipped
  leading column has tens of distinct values and not where it has
  millions.
- It silently weakens the usual plan assertion. A test asserting only
  that a plan is not a `Seq Scan` passes on 18 against a skip scan, so it
  will not catch a missing index. Assert the expected index BY NAME. Skip
  scan also only appears at scale: at a few hundred rows the same query
  seq-scans because the whole table is cheaper than any index, so a plan
  test needs enough seeded rows (~600 was the threshold for this table)
  plus ANALYZE before the planner separates the candidates at all.

Landed as migration 0040 with a plan test in
`MembershipDriverIndexPlanTests`. See [[ddl-probe-container-version]].

*References: ddl-probe-container-version*

*Observed 2026-09-10 (db-admin)*

---
role: "db-admin"
class: domain
topic: "postgres18-skip-scan-changes-index-necessity"
description: "PostgreSQL 18 skip-scans a non-leading index column, so a predicate that needs an index on 16 may already be served on 18"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 970dbfd648338a4f
  - fad468e1bb23ee17
---

## Correction of the postgres18-skip-scan slice: its ADR-028 is gzapp's and its migration 0040 is folded into gzapp's baseline; the field claim is unchanged.

PostgreSQL 18 can use a btree index for a predicate that constrains only a NON-leading
column, probing once per distinct value of the leading column. This is a skip scan,
visible as a high `Index Searches` count in `EXPLAIN ANALYZE`. It breaks the pre-18 rule
of thumb that a predicate without the index's first column cannot use the index. That
rule still holds on 16 and 17, so a probe on the wrong major gives a confidently wrong
answer about whether an index is needed. Probe on the major CI runs.

Measured in gzapp on `operator_driver_membership`, which has a partial unique index on
`(operator_id, owner_driver_id) WHERE status='active'`. The gzapp ADR-028 severance
sweep filters on `owner_driver_id` alone. On 400k rows across 40 operators, PG18 chose
that index anyway: 41 index searches, 166 buffers. The cost tracks the number of
operators, not rows.

What to carry:

- **A skip scan is a real plan, not a good one.** It beats a seq scan and loses badly to
  a seek. Read it as "the predicate is survivable", never as "the index review is
  finished". It is acceptable when the skipped leading column has tens of distinct
  values, not millions.
- **It weakens the usual plan assertion.** A test asserting only "not a Seq Scan" passes
  on 18 against a skip scan, so it will not catch a missing index. Assert the expected
  index by name.
- **It only appears at scale.** At a few hundred rows the same query seq-scans. A plan
  test needs enough seeded rows (about 600 for that table) plus ANALYZE before the
  planner separates the candidates.

The dedicated index and its plan test (`MembershipDriverIndexPlanTests`) landed as gzapp
migration 0040, since folded into gzapp's `0001_baseline.sql` (fourth baseline reset).

Related: [[ddl-probe-container-version]].

*References: ddl-probe-container-version*

*Observed 2026-10-10 (db-admin)*

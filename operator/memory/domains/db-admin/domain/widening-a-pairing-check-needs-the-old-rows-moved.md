---
role: "db-admin"
class: domain
topic: "widening-a-pairing-check-needs-the-old-rows-moved"
description: "Before re-adding an \"all set or all NULL\" CHECK with a new column, or a CHECK binding a state the old writer still writes — the old rows fail it; move them first with a TRUE value, and a control run on main tells whose reds remain"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - c892fd371975283f
---

## Before re-adding an "all set or all NULL" CHECK with a new column, or a CHECK binding a state the old writer still writes — the old rows fail it; move them first with a TRUE value, and a control run on main tells whose reds remain

0024 (j36, 2026-10-25, commit 59d22ac6b) added `snapped` to 0023's
point_set group (`(would_attach_count IS NULL) = (snapped IS NULL)`).
Every stored row with a point has snapped NULL, so re-adding the CHECK
refuses them, and the migration fails on any database that is not
empty. The writer's spec did not list this. The fix was an UPDATE to a
value that is true, not a convenient one: PR 8's consolidator never
snapped, so `false`. The same shape applied to
stop_demands_dropoff_bound: 0022's open dropoffs moved to
awaiting_boarding before the CHECK went on.

The same CHECKs also reddened the PR's own writers: an insert writing
'open', and an INSERT that omits the column. A control run of that
test class on unchanged main (5/5 green) is what showed those reds
belong to the writer change, not to the migration.

**How to apply:** for each widened group or state CHECK, ask "which
existing rows fail this?" Probe it at N-1 with legacy rows, and test
the UPDATE by lifting the CHECK inside a transaction and re-running
the file ([[a-test-that-copies-the-sql-tests-the-copy]]). Report the
writer reds with the control. Related: [[a-seeded-policy-revision-becomes-the-served-one]]:
v2 moved two asserts again.

*References: a-seeded-policy-revision-becomes-the-served-one, a-test-that-copies-the-sql-tests-the-copy*

*Observed 2026-10-24 (db-admin)*

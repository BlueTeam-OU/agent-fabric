---
role: "db-admin"
class: domain
description: A Postgres CHECK constraint built from OR/equality over a nullable column passes vacuously when that column is NULL
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 09c2cbde87d6bf59
  - 0d8a14ec2688acf4
  - 12d8005c8fd09762
  - 5cc6187b7a6613d6
  - 7070c130c46139cd
  - a584613214f09d83
  - d17dac627a4f0931
---

## A Postgres CHECK constraint built from OR/equality over a nullable column passes vacuously when that column is NULL

In PostgreSQL a CHECK expression evaluates to UNKNOWN (not FALSE) when it references a NULL operand, and UNKNOWN passes a CHECK the same as TRUE. The recurring instance found in migration-DDL review here: `CHECK (guard_col IS NULL OR other_col = value)` is meant to say "once guard_col is set, other_col must equal value", but if the compared column is itself NULL, the equality evaluates to NULL, the OR short-circuits, and the row is silently accepted. A live PostgreSQL 16 test confirmed inserting a 'locked' row with a NULL anchor column, then updating the value the lock was supposed to freeze, with zero constraint violation. The fix is an explicit IS NOT NULL guard on every column the constraint depends on (`CHECK (guard_col IS NULL OR (other_col IS NOT NULL AND other_col = value))`), or a companion CHECK forcing the two columns null/non-null together. A hand-written test asserting "the constraint rejects an invalid update" can itself pass vacuously if it doesn't independently populate every column the CHECK reads, so treat every nullable-column CHECK as needing an explicit NULL-path test case, not just a happy-path one.

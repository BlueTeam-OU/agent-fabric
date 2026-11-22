---
role: "architect-cto"
class: domain
topic: "reflection-a-new-status-written-by-an-operation-needs-a-backfill"
description: A status written by an operation reaches only rows changed after it lands; the migration that adds the value backfills the rows already in that state, so the status means one thing for every row and readers carry no second predicate
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - edeba1bcd1958f29
---

## A status written by an operation reaches only rows changed after it lands; the migration that adds the value backfills the rows already in that state, so the status means one thing for every row and readers carry no second predicate

gzapp 2026-09-19: "ALREADY-severed applicants get no `withdrawn`
unless something backfills them" (01a0b666-46aa); "the migration that
adds the value backfills `withdrawn`, so the status means 'closed by
severance' for every row and the queue keeps no driver_staff join"
(01a0b667-6eab). infra/db/migrations/README.md says only that
backfills do nothing on a fresh database (checked 2026-10-23).

*Observed 2026-10-23 (architect-cto)*

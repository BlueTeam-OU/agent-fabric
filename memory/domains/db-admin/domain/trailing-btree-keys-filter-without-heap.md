---
role: "db-admin"
class: domain
topic: "trailing-btree-keys-filter-without-heap"
description: For an ORDER BY x LIMIT n poll with extra filters, put the filtered columns AFTER x in the btree — they are checked on the index entry, so skipped rows cost no heap visit (PG18).
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - ab3ece4f47348770
---

## For an ORDER BY x LIMIT n poll with extra filters, put the filtered columns AFTER x in the btree — they are checked on the index entry, so skipped rows cost no heap visit (PG18).

A poll shaped `WHERE <partial predicate> AND a <= now() AND b = ANY(@set) ORDER BY x
LIMIT n` gets its best index from `(x, a, b)` over the same partial predicate. Postgres
18 uses the trailing keys as Index Conds that are not leading: they don't narrow the
range scanned, but each index entry is tested against them, so rows that don't qualify
are skipped without a heap fetch. The ORDER BY on x still stops the scan at LIMIT.

Measured for 0009, `outbox_messages_due_idx` (98ae121bb), with 25,300 unconsumed rows,
300 of them due to the polling host:

| index | buffers | heap rows discarded |
|---|---|---|
| `(created_at)` | ~4,400 | 25,000 |
| `(created_at, next_attempt_at)` | ~270 | 5,000 (the other host's type, found on the heap) |
| `(created_at, next_attempt_at, message_type)` | ~280 | 0 |
| `(next_attempt_at)` | ~180 | 5,000, plus a top-N sort of every due row |

**Why:** an index led by the filter column looks cheapest in a probe with a small due
set. But it sorts the whole due set, which after an outage is the entire backlog.

**How to apply:** for any queue-style poll (outbox, wakes, leases), lead with the order
column and put the filters after it. Probe with a backlog that is mostly not-due and
foreign rows (the pg-probe skill). Related: [[postgres18-skip-scan-changes-index-necessity]].

*References: postgres18-skip-scan-changes-index-necessity*

*Observed 2026-10-08 (db-admin)*

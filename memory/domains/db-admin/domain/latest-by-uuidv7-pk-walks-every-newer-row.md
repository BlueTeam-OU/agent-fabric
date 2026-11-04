---
role: "db-admin"
class: domain
topic: "latest-by-uuidv7-pk-walks-every-newer-row"
description: "WHERE key = @k ORDER BY <uuidv7 pk> DESC LIMIT 1 looks cheap in a probe and costs the whole table for an idle key; and an index on a column the hot UPDATE rewrites kills HOT"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 3f190eea5c549604
---

## WHERE key = @k ORDER BY <uuidv7 pk> DESC LIMIT 1 looks cheap in a probe and costs the whole table for an idle key; and an index on a column the hot UPDATE rewrites kills HOT

Measured 2026-10-20 for 0021 (53429b633, #1150), postgres:18-alpine,
vehicle_runs 141,000 rows: `SELECT ... WHERE physical_vehicle_id = @v ORDER BY
run_id DESC LIMIT 1` plans as a backward scan of the primary key with the key
as a Filter. For a vehicle that ran an hour ago it read 13 buffers; for one last
seen 6 days ago, 105,105 (~820 MB) — it walks every newer row of every vehicle.
`max(last_evidence_at)` with an index on the key alone read 3-143.

Second half: the two-column index (key, last_evidence_at) was index-only and
cheapest per read, but the per-batch UPDATE rewrites last_evidence_at, and HOT
fell from 94% to 0% with the table 3.5x larger. The read ran once per vehicle
after a crash; the update on every sample. Key-only index won.

**Why:** a probe whose seed has every key recently active never shows the idle
case, and a per-read buffer count hides what an index costs the writer.

**How to apply:** probe "latest per key" reads with one idle key seeded far in
the past; before indexing a column, list the hot UPDATEs that set it and measure
HOT with each candidate (drop the previous candidate first —
`LIKE ... INCLUDING ALL` copies a stray one). Related:
[[trailing-btree-keys-filter-without-heap]], [[a-plan-test-mutation-must-change-the-plan]].

*References: a-plan-test-mutation-must-change-the-plan, trailing-btree-keys-filter-without-heap*

*Observed 2026-10-20 (db-admin)*

---
role: "db-admin"
class: domain
topic: "an-fk-check-needs-a-full-index-on-the-referrer"
description: "A partial index on the referencing column (open rows only, live statuses only) leaves every parent DELETE's FK trigger a seq scan of the child — measured 47 s and 370 s for one sweep; size the referrer index for the delete, not the hot read"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - c683f02a4a258e2e
---

## A partial index on the referencing column (open rows only, live statuses only) leaves every parent DELETE's FK trigger a seq scan of the child — measured 47 s and 370 s for one sweep; size the referrer index for the delete, not the hot read

Measured 2026-10-21 for 0022 (j33, postgres:18-alpine, 128,010 stop_calls,
108,010 stop_directives): the plan proposed `stop_calls (run_id, …) WHERE state
IN (open states)` and `stop_directives (stop_call_id) WHERE status IN (live)`.
The retention sweep deletes CLOSED parents; each delete fires the child's RI
check `SELECT 1 FROM child WHERE fk = $1`, which no open-only/live-only partial
index can answer. Run sweep (2,000 deletes): FK trigger 47.4 s vs 0.39 s with a
full (run_id, …) index. Call sweep (20,000 deletes): 370 s vs 4.3 s.
A partial `WHERE fk IS NOT NULL` IS usable (`fk = $1` implies it).

**Why:** EXPLAIN of the DELETE shows the parent scan, not the trigger's; only
`Trigger for constraint …: time=` in EXPLAIN ANALYZE reveals it.

**How to apply:** for every FK whose parent is ever deleted (sweeps included),
the child needs an index leading the FK column over ALL rows (or `IS NOT NULL`).
Read the trigger times, not just the plan. Pin it with an EXPLAIN of the RI
lookup over closed rows, mutated to the partial form. Related:
[[gzapp-retention-sweeps-need-no-index-at-6h]], [[a-plan-test-mutation-must-change-the-plan]].

*References: a-plan-test-mutation-must-change-the-plan, gzapp-retention-sweeps-need-no-index-at-6h*

*Observed 2026-10-21 (db-admin)*

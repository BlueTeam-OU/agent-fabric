---
role: "db-admin"
class: domain
topic: "join-to-a-mostly-ended-parent-hashes-it-all"
description: "\"Open children whose parent has ended\" as a plain join makes the planner hash every ended parent; no index fixes it, the query shape does"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 8d61f0461f4defcf
---

## "Open children whose parent has ended" as a plain join makes the planner hash every ended parent; no index fixes it, the query shape does

A query for "open children whose parent has ended" (open stop_calls JOIN
vehicle_runs WHERE r.ended_at IS NOT NULL) is normally empty. But the
planner sees 144 of 145 parents ended and estimates nearly every child
joins one. So it hashes the whole parent table: a seq scan of 2,786 pages
plus a temp spill at default work_mem, 290 ms. No index helps, because
8,000 PK probes really do cost more than one scan.

The fix is the query shape. Anti-join the OPEN parents through their
partial index (NOT EXISTS ... ended_at IS NULL), then read the parent's
columns with a correlated scalar subquery. That subquery runs only for
the rows that survive: 255 buffers, 5.6 ms. It is equivalent when the FK
guarantees the parent exists.

Measured 2026-11-10 (j49, postgres 18.6, 145,000 runs, 8,000 open calls)
on StopCallRepository.ListOpenOnEndedRunsAsync, which runs every 5 s.
Sent as OBSERVATION 01a1c4f5 to backend-dev-01, who took it onto #1238.

**Why:** the estimate for the ended side cannot see that "open child on
ended parent" is transient, so the plan is right for the estimate and
wrong for the data.

**How to apply:** in an index review, when a join's estimate is large and
its actual output is about 0, look at the query shape before the index.
Show both shapes' buffers, plus a control with a few parents ended so the
rewrite returns rows. Related: [[an-fk-check-needs-a-full-index-on-the-referrer]],
[[stop-call-index-review-2026-11]].

*References: an-fk-check-needs-a-full-index-on-the-referrer, stop-call-index-review-2026-11*

*Observed 2026-11-10 (db-admin)*

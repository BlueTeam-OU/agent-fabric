---
role: "architect-cto"
class: domain
topic: "reflection-sqlite-covering-index-over-virtual-generated-columns-is-a-search"
description: "W44 — in SQLite an index that includes a VIRTUAL generated column is not used as a covering index: the planner recomputes the column from the row (USING INDEX, not USING COVERING INDEX); name an index meant to cover over the table's…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - a66bcb6c433d2e4f
---

## W44 — in SQLite an index that includes a VIRTUAL generated column is not used as a covering index: the planner recomputes the column from the row (USING INDEX, not USING COVERING INDEX); name an index meant to cover over the table's stored columns and pin it with an EXPLAIN QUERY PLAN test

2026-10-27, InterWeave #489 (human store v10): the badge and hidden counts needed covering indexes; the first text named the tables' generated `source_endpoint_key`/`channel_key` (VIRTUAL, IFNULL of the real column). rust-ui-dev-02's plan test showed SQLite planning `SEARCH ... USING INDEX (kind=?)` and re-reading every row; over the stored columns `source_endpoint, channel_id` the plan is `USING COVERING INDEX`.

**Why:** a VIRTUAL generated column is computed on read; SQLite does not take its value from an index entry, so the row is fetched.

**How to apply:** write a covering index over stored columns (or make the generated column STORED if it must be in the cover); pin "covering" with a test on `EXPLAIN QUERY PLAN` that fails when the index is dropped. Related: [[reflection-a-column-in-state-md-s-row-may-be-a-later-stage-s]].

*References: reflection-a-column-in-state-md-s-row-may-be-a-later-stage-s*

*Observed 2026-10-27 (architect-cto)*

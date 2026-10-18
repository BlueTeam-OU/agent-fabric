---
role: "web-dev"
class: domain
topic: "tanstack-invalidate-joins-first-read"
description: "why invalidateQueries after a write can still show pre-write data — it joins a first read that has no data yet"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - fafd6326432eeeea
---

## why invalidateQueries after a write can still show pre-write data — it joins a first read that has no data yet

In TanStack Query 5 (query-core 5.104.1, `Query.fetch`), the refetch an
`invalidateQueries` starts cancels a running fetch only when the query
already holds data (`state.data !== undefined && cancelRefetch`). A query
still on its FIRST read is joined instead, and when that read answers with
state from before the write, the cleared invalidation means nothing re-reads
it. A sibling query on the same page (a polled card) and a per-filter list key
picked while the write was out are exactly the queries in that state.

The fix is `cancelQueries({queryKey}).then(() => invalidateQueries({queryKey}))`.
Cancel defaults to `revert: true`, so it reverts the pending read to idle without
writing its result, and the invalidation then reads anew. Neither `refetchQueries`
(it takes the same `fetch` path) nor `resetQueries` (it flashes a skeleton) fixes it.
gzapp #1115 has the helper `readAnew` in `apps/admin_web/src/features/stops/api.ts`.
A test holds the first read in a deferred promise, settles the write, releases the
read with the old data, and asserts the new data and two reads.

**Why:** found by the second-engine review of #1115. The acts' tests only
counted GETs and always served the same data, so they could not see it.

**How to apply:** any `onSettled` invalidation of a query that can be on its
first read when the write settles. The rest of admin_web's ~34
`invalidateQueries` sites have not been audited for it.

*Observed 2026-10-13 (web-dev)*

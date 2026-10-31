---
role: "backend-dev"
class: domain
topic: "insert-guard-does-not-bound-commit"
description: "A reader that serves closed time windows needs the writer bounded from stamp to COMMIT on the reader's clock; a WHERE clock_timestamp() guard only bounds statement start"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - aa3522fc3051482d
---

## A reader that serves closed time windows needs the writer bounded from stamp to COMMIT on the reader's clock; a WHERE clock_timestamp() guard only bounds statement start

When a reader promises that a closed window reads the same ever after,
the writer must not let any row land in that window after it closes. That
promise needs a bound on the whole path from when the writer stamps the row
to when the row becomes visible. Two gaps were found one after another on
the stop-call shadow writer (#1159, then #1167):

1. The row is stamped in process, then several round trips run before the
   INSERT. Fix: `INSERT ... SELECT ... WHERE @stamp > clock_timestamp() -
   @maxLag`. It uses the **database** clock, the same clock the reader closes
   windows on, so skew between hosts drops out. A refused row is counted,
   never silently dropped.
2. That guard is read when the statement *starts*, but the row becomes
   visible at *commit*. A synchronous-replication wait with a standby down
   can hold the commit indefinitely. Fix: the insert runs in its own
   transaction with `SET LOCAL synchronous_commit = local`, which is free on
   an UNLOGGED table because its rows never reach a standby. Add a
   `statement_timeout`, and count a timeout like a late row. The
   contract states the residual seconds-long local-flush window.

**How to apply:** for any windowed or immutable-once-served read, ask where
the writer's deadline is enforced and when its row becomes visible, and
bound both on the reader's clock. Test it with a stale stamp and with a
lock held by another session. See [[shadow-write-in-live-tx-needs-savepoint]]
for the other shadow-writer trap.

*References: shadow-write-in-live-tx-needs-savepoint*

*Observed 2026-10-25 (backend-dev)*

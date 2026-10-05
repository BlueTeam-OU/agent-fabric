---
role: "p2p-network-dev"
class: domain
topic: "race-tests-need-the-current-thread-runtime"
description: "A select! race between a finished task's join and a signal another task sets is invisible on tokio's multi-thread runtime (LIFO slot); reproduce it on current_thread"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2781dfc27bdae510
---

## A select! race between a finished task's join and a signal another task sets is invisible on tokio's multi-thread runtime (LIFO slot); reproduce it on current_thread

A `tokio::select!` race between two arms that become ready "together" — a JoinSet task that
finishes AND, inside the same poll, wakes a second task that then flips a watch the select also
reads — almost never shows on the multi-thread runtime: the task woken LAST (the select's owner,
by the join) takes the worker's LIFO slot and runs before the other one sets the signal. So a
regression test there passes WITHOUT the fix (measured, j14, ipc-server `end()` discarding a
finished `admin.shutdown` answer when `stop` won: 32 iterations, mutant green). On
`#[tokio::test(flavor = "current_thread")]` the scheduler is FIFO, the signal-setter runs first,
both arms are ready at the next poll, and the unbiased select loses about half the time: the
mutant failed on the first iteration. In production (desktop-e2e, 1 in 12) work stealing opens
the window.

**Why:** a race test that only passes is not proof; the mutation is.
**How to apply:** for a select between a completion and a signal derived from it, write the test
on current_thread, loop it ~32 times, and mutate the fix back to watch it fail. The fix shape:
on ending, `abort_all()` and then join, answering every `Ok`. Abort leaves a task that already
completed with its output, so answers that were ready are still delivered. See
[[cancel-a-future-after-one-poll]].

*References: cancel-a-future-after-one-poll*

*Observed 2026-10-04 (p2p-network-dev)*

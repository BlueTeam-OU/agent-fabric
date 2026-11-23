---
role: "web-dev"
class: domain
topic: "tanstack-answer-needs-a-timer-flush"
description: "Under vi.useFakeTimers a TanStack query's answer reaches the screen only after a zero-delay timer runs; microtask flushes are not enough."
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - f53c334a16b0a92a
---

## Under vi.useFakeTimers a TanStack query's answer reaches the screen only after a zero-delay timer runs; microtask flushes are not enough.

Moving PlaceSearchField from a hand-rolled fetch effect to a TanStack query
(gzapp, 26f48b1ae, 2026-11-14) broke tests that settled the answer with two
`await Promise.resolve()` inside act(): TanStack's notifyManager batches
observer updates on a zero-delay timer, so under fake timers the list,
"nothing found" and the Enter pick all saw the previous render.

**Why:** the failures looked like component bugs (Enter not picking, empty
state not shown) and cost a debugging round.

**How to apply:** after the debounce, settle with
`await act(async () => { await vi.advanceTimersByTimeAsync(10) })`, not
microtask ticks. Related: [[a-dataless-refetch-clears-iserror]],
[[await-what-only-the-target-state-renders]].

*References: a-dataless-refetch-clears-iserror, await-what-only-the-target-state-renders*

*Observed 2026-11-14 (web-dev)*

---
role: "rust-ui-dev"
class: domain
topic: "commit-show-before-awaiting"
description: "A client command that commits state must hand its update to the view before it awaits the network; an inline first attempt hides the committed row and coalesces away \"Sending\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c0333c201842f320
---

## A client command that commits state must hand its update to the view before it awaits the network; an inline first attempt hides the committed row and coalesces away "Sending"

When the facade command that commits a send, retry or restore then awaits the first transport
attempt inline, and the UI loop hands a command's updates over only once the command returns,
the person sees nothing until the network answers:
- against an unreachable peer, a restored row was absent for 30 s or more after Undo (1 run in
  3 on a phone; the others were quick only because the failure was quick);
- Retry never showed "Sending": that state was committed and replaced inside one command, so
  the view only ever got the state after the attempt.

The rule: a command commits and reports, then returns. The attempt runs on the next tick of the
loop that owns the dependency, so the committed state reaches the view first and every
intermediate state the person must see is rendered. Before moving the attempt, ask the
facade's other owner whether anything relies on the inline timing. Then adapt the callers'
tests to the new order first, and check them green against the old facade too.

**Why:** it is the same rule as "show only what the store agreed to", applied the other way
round: what the store did agree to must not wait on a slow dependency to become visible.
**How to apply:** when a view state lags or never appears on a device, look first for an await
between a commit and the hand-over of its update. Related:
[[uncertain-outcome-state-and-copy]], [[ui-thread-wakeups-bounded]].

*References: ui-thread-wakeups-bounded, uncertain-outcome-state-and-copy*

*Observed 2026-10-18 (rust-ui-dev)*

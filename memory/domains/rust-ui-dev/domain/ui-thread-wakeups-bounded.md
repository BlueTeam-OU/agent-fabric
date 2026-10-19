---
role: "rust-ui-dev"
class: domain
topic: "ui-thread-wakeups-bounded"
description: "Bridging a worker thread to a Slint window -- invoke_from_event_loop per message is an unbounded queue; bound the channel and coalesce the wake-up"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95135f9cd09890e8
---

## Bridging a worker thread to a Slint window -- invoke_from_event_loop per message is an unbounded queue; bound the channel and coalesce the wake-up

Between a background (facade/network) thread and the Slint event loop there are two queues,
and both grow without bound while the window stalls: the channel carrying updates, and
slint::invoke_from_event_loop, which queues one closure per call. A drain rate (N per turn)
is not a memory bound. Bound the update channel, coalesce state updates (latest wins) so a
full queue loses nothing the store holds, and post at most one wake-up closure while one is
pending (an atomic flag cleared by the window when it drains). Test: a stalled window holds
the queue at its bound and the store-backed items are all shown after it resumes.

*Observed 2026-10-15 (rust-ui-dev)*

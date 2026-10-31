---
role: "rust-ui-dev"
class: domain
topic: "slint-zero-timers-no-order"
description: "Two Slint zero-delay timers scheduled in one turn fire in no promised order; coalesce \"latest wins\" requests into one scheduled task"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 572fa39186754498
---

## Two Slint zero-delay timers scheduled in one turn fire in no promised order; coalesce "latest wins" requests into one scheduled task

In Slint 1.18.1, `slint::Timer::single_shot(Duration::ZERO, f)` twice in the same
event-loop turn does not promise first-in, first-out. InterWeave's ui-slint `defer`
is that call. One render asked focus for a row button that was about to go, and
the next asked for the next row's. Both fired in one `update_timers_and_animations`,
the stale one last, and focus stayed in a dialog that had already closed. It was
seen in a view test only when no turn ran between the two renders
(InterWeave feat/j111-android-recovery 5b3b2cff, 2026-10-19).

**Why:** a request whose meaning is "the latest wins" (focus, scroll-into-view,
a status line) is applied wrongly when an earlier one runs after it.
**How to apply:** keep one pending slot (`Rc<RefCell<Option<T>>>`). A new
request replaces the value, and only the first schedules the task, which takes
the latest value. Route every site of the same kind through it: in that fix the
swipe's focus moves and the trust dialog's share one slot. A test reproduces the
race by making both requests with no timer update between them.

*Observed 2026-10-19 (rust-ui-dev)*

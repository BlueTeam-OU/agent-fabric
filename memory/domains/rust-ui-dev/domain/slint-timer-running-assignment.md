---
role: "rust-ui-dev"
class: domain
topic: "slint-timer-running-assignment"
description: in Slint, a Timer that sets self.running = false in triggered drops its running binding forever; use a fired flag reset per press
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 054f2b775266912f
---

## in Slint, a Timer that sets self.running = false in triggered drops its running binding forever; use a fired flag reset per press

A Slint `Timer { running: <binding>; triggered => { self.running = false; ... } }` loses its binding on that assignment (assigning a property with a binding removes the binding), so the timer never runs again for that element. In InterWeave both long-press timers (message row, proposal card) did this: a second long press on the same row opened nothing (found 2026-10-27, fixed 93f29a06 on #471 with a `fired` property on the TouchArea, reset on pointer down, `running: ... && !fired`).

How to apply: never assign a bound property from inside the element's own callbacks; add a state flag to the binding instead. Tests: a second long press on the same row (tests/pointer.rs `a_second_long_press_on_a_row_opens_its_menu_again`).

*Observed 2026-10-27 (rust-ui-dev)*

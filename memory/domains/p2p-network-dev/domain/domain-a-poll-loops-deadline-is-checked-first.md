---
role: "p2p-network-dev"
class: domain
topic: "domain-a-poll-loops-deadline-is-checked-first"
description: "a poll loop's deadline assert goes at the top of the body (or after the done check), never after the work: an iteration that finishes the wait past the deadline otherwise fails a run that held"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 4459c5287bb878b4
---

## a poll loop's deadline assert goes at the top of the body (or after the done check), never after the work: an iteration that finishes the wait past the deadline otherwise fails a run that held

**The shape that flakes under load** is `while !done { work_that_may_set_done; assert!(now < deadline); sleep }`. The last iteration's work completes the wait. Then, if the clock is past the deadline, the assert fails before `done` is read again. The failure message itself shows the state reached (InterWeave `identity_recovery.rs:566`: "A received direct true, broadcast true").

**The fix** moves the assert to open the body, or places it after a `if done { break }`. The deadline then bounds when an attempt may start, and the condition is always read first.

**A body that cannot change the condition** is safe with the assert anywhere. Examples are a body that only checks a child's exit, or one that only drops a probe.

**Find the class by scan, not by eye.** Look for every deadline assert inside a `while` body that has statements before it, then read each one. On 2026-10-26 the scan found 13. Nine had the flaw: seven in p2p-network-dev's tests (InterWeave #459) and two in rust-ui-dev's human_app (#451, df7a2d4c). Every `loop`-form poll loop already asserted first.

**What asserting first leaves open:** a body that WAITS (a 500 ms receive window, `arriving()` in security-local) can still finish its work up to one window past the deadline and pass. Bound the last wait by the time left, `window.min(deadline.saturating_duration_since(now))` — #459's review F1, carried as j78. #459 merged 81d72849 on 2026-10-26.

*Observed 2026-10-26 (p2p-network-dev)*

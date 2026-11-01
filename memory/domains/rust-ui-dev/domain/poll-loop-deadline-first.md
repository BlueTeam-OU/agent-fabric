---
role: "rust-ui-dev"
class: domain
topic: "poll-loop-deadline-first"
description: "Writing a test's poll-until-deadline loop -- check the condition right after the iteration's work and assert the deadline only when it is still false, or a run where the state held fails under load"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 15723951e7fd05ce
---

## Writing a test's poll-until-deadline loop -- check the condition right after the iteration's work and assert the deadline only when it is still false, or a run where the state held fails under load

The flake shape is `while !cond { work(); assert!(now < deadline); sleep }`. When the work that
makes `cond` true lands after the deadline, the assert fires before `cond` is read again, and
the message even shows every flag true. This is a class, not one test: one scan of
`assert!(Instant::now() < deadline` placed after other statements in a `while` body found 13
hits across two roles' tests; at least 9 had the flaw.
Correct shape: `loop { work(); if cond { break } assert!(now < deadline, "<state>"); sleep }`,
or put the deadline check at the top, before the work. A body that only checks something which
cannot make the condition true (a child's exit) is sound as written.
How to apply: when you write or review a poll loop, find the line that can make the
condition true and confirm that the condition is read between it and the deadline assert. When
one instance shows up, grep the role's whole test tree for the shape and fix every instance.
Related: [[e2e-waits-from-dependency-cadence]].

*References: e2e-waits-from-dependency-cadence*

*Observed 2026-10-27 (rust-ui-dev)*

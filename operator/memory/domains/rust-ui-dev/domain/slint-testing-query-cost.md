---
role: "rust-ui-dev"
class: domain
topic: "slint-testing-query-cost"
description: "i_slint_backend_testing find_all in a per-turn test helper costs seconds on a big tree; find_first forces the same layout"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 03610301db49a8e9
---

## i_slint_backend_testing find_all in a per-turn test helper costs seconds on a big tree; find_first forces the same layout

On Slint 1.18.1's testing backend, `ElementQuery::from_root(..).find_all()`
walks the whole element tree. Called twice per turn in a test's `turn()`
helper, it took 4.4 s (unloaded) on the turn that lets go of 200 held rows,
and under the workspace suite's load it ran out a 10 s `until` wait.
That was InterWeave j215, `apps/human-desktop/tests/window_faults.rs`,
at_the_session_bound... "B open"; 4 of 16 parallel copies failed.

Measured on 2026-11-05 at commit 3f3e1d2cf (PR #578):
- The QUERY is what lays the tree out, not the `absolute_position()` read
  that follows it. With the read removed, all 6 tests pass. With the query
  removed, the 3 paging tests time out.
- `find_first()` forces the same layout and stops early: 0 of 16 fail
  at the same load.

How to apply:
- A helper that only forces layout uses `find_first`.
- A timeout under load: time the helper's own parts first. Here
  `app.pump` took 5-115 ms, and the test helper was the cost.
- To reproduce: run N copies of the one test binary in parallel
  (`--exact <name>`). See [[desktop-e2e-load-flakes]].

*References: desktop-e2e-load-flakes*

*Observed 2026-11-05 (rust-ui-dev)*

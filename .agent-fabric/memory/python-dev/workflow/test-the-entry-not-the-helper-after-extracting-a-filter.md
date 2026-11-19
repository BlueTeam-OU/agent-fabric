---
role: "python-dev"
class: workflow
topic: "test-the-entry-not-the-helper-after-extracting-a-filter"
description: "j124 #619 — extracting a filter into a helper makes tests of the helper green when the entry stops calling it; test through the entry with mocks, assert the kept row too"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7188db43289c935e
---

## j124 #619 — extracting a filter into a helper makes tests of the helper green when the entry stops calling it; test through the entry with mocks, assert the kept row too

j124 (#619): I factored the pair filter of tests/live_interweave_two_accounts.py into `pair_of()` and tested only the helper; the review (P2) deleted the call in `judged_roster` and the suite stayed green. The fix patches `R.load`, `R.valid_rows`, `GitMainKeys`, `paths.operator_root`, `LOGIN`, `PEER` on the module objects and renders through the real entry. A mutation `(LOGIN, PEER)` -> `(LOGIN, LOGIN)` is invisible to "third row absent" assertions: also assert the peer IS present.

**Why:** the review class caught it by one-line mutation of the entry, not the helper.
**How to apply:** after extracting a helper, mutate the call site once before the review; positive-control every "X absent" with "Y present". See [[mutation-run-read-rc-not-fail-count]].

*References: mutation-run-read-rc-not-fail-count*

*Observed 2026-11-14 (python-dev)*

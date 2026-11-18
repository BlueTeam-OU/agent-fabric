---
role: "python-dev"
class: workflow
topic: "work-module-setups-force-states-the-table-forbids"
description: "j101: after the work module, a test setup that reaches a state by a verb the table forbids must force it; how, and the traps met"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1681b78754edb81b
---

## j101: after the work module, a test setup that reaches a state by a verb the table forbids must force it; how, and the traps met

Since #521 (j101) every `fabric-jobs` verb asks its rule-14 row's needs, so old suites that did `done` on a queued job, `deliver` of free text, `block` on words or `pause` with no pushed branch fail at the setup, not at the case.

**Why:** the rows are the contract (tools/fabric/work/table.py, held to the ADR by tests/test_work_table.py); the characterisation suites pin each verb's needs (tests/test_work_lifecycle*.py).

**How to apply:**
- A suite about something else forces the state: edit the list as another writer (`identity.update_jobs`, or a `force()` helper writing with `sort_keys=True, indent=2` when the listing is compared byte for byte), or, in-process, `mock.patch.dict(needs.NEEDS, {name: lambda job, fields, who: [...]})` as tests/test_jobs_switch.py `sw` does (`strict` is the command as it is).
- A forced `done` leaves `doc["last"]` unset; on a fast host two jobs tie on a one-second stamp and `last_worked` leaves the wrong one (Fedora CI, #521). Set `last` in the test.
- `deliver` on a PR that merged is refused ("done, not delivered"): to reach `done` legitimately, deliver it while the fake gh says OPEN, then flip it to MERGED.
- Run suites with CI's environment (strip `AGENT_FABRIC_*`): with AGENT_FABRIC_ROOT set, the intake test loaded the main checkout's jobs.py, not the worktree's.
- A fixture fabric that copies tools/ needs `by_path.py` and `work/` beside `jobsparts/` (tests/test_launch_cli.py).
- See [[review-report-extract-walk-json-strings]]: extract a re-review report with `"review_round": N` and without `agent-fabric-review v2` in it, or post-review refuses a quoted marker.

*References: review-report-extract-walk-json-strings*

*Observed 2026-11-09 (python-dev)*

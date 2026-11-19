---
role: "python-dev"
class: solution
topic: "block-on-request-refusal-needs-journaled-id-in-every-suite"
description: "j746/j754 — block --on request:<id> now refuses ids the journal lacks, and start skips the copy need for a no-branch job; fixtures that block on a made-up id or start a copy-less queued job break"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1d0a321ac280fa88
---

## j746/j754 — block --on request:<id> now refuses ids the journal lacks, and start skips the copy need for a no-branch job; fixtures that block on a made-up id or start a copy-less queued job break

`fabric-jobs block --on request:<id>` / `--on-request` (jobsparts/blockers.py `unreadable_request`, called from verbs.block_fields) refuses an id with no row of its own and no inbound reply naming it in this login's journal. Every suite that blocked on an invented id (test_jobs, test_jobs_transfer, test_jobs_blockers, test_work_lifecycle*, test_jobs_switch) had to journal the message first (`gzcoord-out-pending` + `gzcoord-out-final --state accepted`, or `gzcoord-in`) and give the journal an owner (`AGENT_FABRIC_SECRET_STORE` with `.agent-id`).

`start` (needs._working_copy, who == "start") needs no working copy for a job with no branch (j754); a fixture that used a copy-less queued job to prove the start refusal must now give it a `branch`. A later `project` re-point refuses a job with a branch, so force it back to None.

j641's `--repoint` was already on main (6ab3e2f0) when the request arrived: read the tree before building a request's item.

**Why:** j108 (PR for j751 j746 j744 j754 j641) hit all of these.
**How to apply:** when changing a `block`/`start` precondition, grep tests for `--on-request` and `"has no working copy"` first.

*Anchors: `tools/fabric/jobsparts/blockers.py::unreadable_request`, `tools/fabric/jobsparts/needs.py::_working_copy`*

*Observed 2026-11-11 (python-dev)*

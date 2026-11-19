---
role: "python-dev"
class: solution
topic: "j134-own-job-blocker-merged"
description: "j134 — a job: blocker on the asker's own login is read from its own list (#543 merged); post-review header trap, CI flake"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c97a4466fb2501c
---

## j134 — a job: blocker on the asker's own login is read from its own list (#543 merged); post-review header trap, CI flake

#543 merged (30886b51): `blockers.check_job` sends `login == identity.current_agent()` to `_from_own_list` (identity.read_jobs, stored state; SystemExit from read_jobs must be caught, run_check's `except Exception` does not catch it). Peer path unchanged.

**Why it mattered:** job-state answers only the sender of the REQUEST the job came from, so an own job taken from another's request refused its own asker for ever.

**Traps:**
- `fabric-pr post-review` needs the `agent-fabric-dispatch v1` block as the report's first lines; the review class only repeats it if the dispatch prompt carries the brief's block verbatim. A hand-assembled report was refused by the classifier; re-dispatch with the block and post the report unedited.
- `fabric-review brief <req.yaml>` (no `render` word), `mode: review`.
- Waiting on tests/run.sh: match `^exit [0-9]+$`, not `^exit ` (a test prints "exit codes").
- test_review_codex flaked once in the full run (/tmp fixtures vanished), passed alone; platform-smoke debian test_reads_live failed once, green on re-run (`gh run rerun <id> --failed`).
- Left open for the coordinator: jobs.py docstring lines ~110, ADR-037 rule 8, blockers.py CHECK paragraph omit the own-list/refusal causes; `_cycle` does not catch SystemExit from read_jobs.

*Anchors: `tools/fabric/jobsparts/blockers.py::_from_own_list`, `tests/test_job_state.py::a job: blocker on this logins own list is read from it`*

*Observed 2026-11-10 (python-dev)*

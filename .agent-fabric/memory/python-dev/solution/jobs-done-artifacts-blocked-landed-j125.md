---
role: "python-dev"
class: solution
topic: "jobs-done-artifacts-blocked-landed-j125"
description: "j125 #541 — fabric-jobs done takes artifacts judged one by one; blocked job with landed branch gets a new branch; test setup traps; deferred F4"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - da4aa9e553b8e08f
---

## j125 #541 — fabric-jobs done takes artifacts judged one by one; blocked job with landed branch gets a new branch; test setup traps; deferred F4

#541 (merged eaa458bd): `fabric-jobs done <id> <artifact>...` records artifacts as evidence (verbs.py move(): each name judged alone with `needs.st.done_evidence` on a one-artifact copy; refused on an already-done job, pointing at deliver). `choose()` in branching.py treats a *blocked*, non-`--repoint` job whose branch `_landed` as having no branch (paused/active still refused).
Open, for a next job: F4 — the per-name check refuses a squash-merged branch excused only by a PR named beside it (joint done_test would pass); settle.py:406 message still says bare `(fabric-jobs done)`; SKILL.md row is the coordinator's (j735).
**Test traps:** a blocker's state is cached at `block` time, so set gh_says to the final state (MERGED) *before* `block --on pr:...`; a past `clock:` blocker is refused at block; `w.sw("done"…)` mocks the needs, use `w.strict` to test the real verb; a World left with an active job breaks the following positive control (use a fresh World). `fabric-review next` needs `fabric-review save <pr> 1 < report` first and `--pr`, not `--report`. Deferral label names the raising head (`b35e1d4f:F3`). `tests/run.sh` waited >2h for the host full-suite lease; queue it early. Minimum for arming was 1 work commit here: dry-run before asking for a word.

*Anchors: `tools/fabric/jobsparts/branching.py::_landed`, `tools/fabric/jobsparts/verbs.py::evidence_only`*

*Observed 2026-11-10 (python-dev)*

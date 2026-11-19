---
role: "python-dev"
class: workflow
topic: "reported-bug-may-be-fixed-on-main-undistributed"
description: "j111: a stale-read report was already fixed by an ancestor commit; reproduce by mutating the fix before writing a new test"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ef2ff3c71bd94d4a
---

## j111: a stale-read report was already fixed by an ancestor commit; reproduce by mutating the fix before writing a new test

j111 (start read a cleared job: blocker as waiting) was already fixed on main by b35847c5 (`decide=True` in `needs._blockers_cleared`); the reporter ran an undistributed fabric.

**Why:** the acceptance asked for a test failing on today's code; none can exist. Removing the one-token fix and running the existing test (`tests/test_jobs_blockers.py`, "delivered inside the ten minutes") failed with the reported symptom, which proved cause and fix in one run.

**How to apply:** before building, `git merge-base --is-ancestor` the suspect fix, grep tests for the symptom, mutate the fix, clear `__pycache__`, run. If it fails as reported, reply with the evidence and close with `done --no-artifact`; do not add a duplicate test. Note a closed job still needs an answer to every REPLY-EXPECTED REQUEST that arrived meanwhile before `switch`.

*Anchors: `tools/fabric/jobsparts/needs.py::decide=True`*

*Observed 2026-11-12 (python-dev)*

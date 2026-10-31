---
role: "python-dev"
class: solution
topic: "jobs-switch-built-255"
description: "fabric-jobs switch/pause built in #255 (2026-10-14); the settle rules, the test world, and the traps the reviews and the stripped suite found"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1bab6b557cc3cd67
---

## fabric-jobs switch/pause built in #255 (2026-10-14); the settle rules, the test world, and the traps the reviews and the stripped suite found

`fabric-jobs switch` (alias `next`) and `pause` landed in agent-fabric #255. Contract: the header of tools/fabric/jobs.py; code in tools/fabric/jobsparts/{settle,branching,vcs}.py and verbs.switch_job.

**Why / traps found**
- Suites that used `next` to take a job need `tests/jobs_world.py` (bare origin per checkout, memory file touched, a merged artifact before `done`): a switch settles the old job.
- Timestamps are one second: "the job last worked" must tie-break on `doc["last"]`; a test that passes alone can fail stripped when two jobs share a second.
- An abbreviated sha can be all digits (1 in 27 at seven chars): never require a letter; a word that is no commit is "not evidence", not "could not tell" (`rev-parse --verify --quiet`, not `cat-file`).
- Owed replies: scope by `recorded_at` (receipt), not `happened_at`; check answered and age before the metadata parse, or an unreadable row can never be cleared.
- The job to take can be the job just left (a blocker that cleared at once): do not settle it.
- A fixture fabric that copies jobs.py needs git.py and gh.py (vcs.py loads them at import).

**How to apply:** when extending switch, plant the mutation per rule against tests/test_jobs_switch.py (it runs in process; the arming count is stubbed at `branching._addable`).

*Anchors: `tools/fabric/jobsparts/verbs.py::switch_job`, `tools/fabric/jobsparts/settle.py::owed_replies`, `tests/jobs_world.py::seeded`*

*Observed 2026-10-14 (python-dev)*

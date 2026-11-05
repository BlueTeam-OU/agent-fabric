---
role: "fabric-coordinator"
class: workflow
topic: "job-sweep-checker-verdicts"
description: "Sweeping my open jobs for done/superseded with read-only checkers — verify every DONE against the job's title before closing"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1328caadf1195c37
---

## Sweeping my open jobs for done/superseded with read-only checkers — verify every DONE against the job's title before closing

2026-11-04, owner: "full verification on remaining jobs". 83 open jobs, four Explore
checkers (batches of ~21, round-robin by id), each returning id | verdict | checkable
evidence. 18 DONE proposed; I closed 15 and kept 3 after reading each job's title:
j395 (byte cap met but the title also asks ≤150-char lines, and MEMORY.md is 230 lines
against the 200-line load limit), j434 (timer runs, age bound and report unchecked),
j45 dropped not done (audit ran, read-back never confirmed, moot after 3 weeks).

**Why:** a checker confirms the headline of a job and skips its second clause; the
read-only fence also refuses `git fetch` for it, so it judges local origin/main refs.

**How to apply:** fetch every repo myself before dispatching; give checkers today's known
facts (merged PRs, distributions) so they don't re-derive them; close only after reading
the job title beside the evidence; a job whose blocker cleared is not thereby done.

*Anchors: `tools/fabric/jobsparts/settle.py::done needs evidence it landed`*

*Observed 2026-11-04 (fabric-coordinator)*

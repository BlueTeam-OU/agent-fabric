---
role: "python-dev"
class: solution
topic: "j49-fabric-jobs-sweep-state"
description: "j49 / PR #282 fabric-jobs sweep: what it reads and closes, review findings fixed, what the owner/coordinator still add on the branch"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7efc6430506bc391
---

## j49 / PR #282 fabric-jobs sweep: what it reads and closes, review findings fixed, what the owner/coordinator still add on the branch

#282 merged 2026-10-16 (5 work, 7 fix; owner's word for the arm, agentd.py is a security-boundary path). `fabric-jobs sweep` (tools/fabric/jobsparts/sweep.py) reuses `settle._landed` + `_reflected`; resolves only owner/repo#N, URLs, `<project> [PR] #N` (registry first github.com remote), `branch:`, a sha beside the job's own project, `reply:`. Any other number (`LEFTOVER`: #N, !N, PR/MR/pull request/merge request N in any spelling) is unresolved and keeps the job delivered; a bare "PR #N" is NOT guessed into the job's own project.

**Why:** seven review rounds each found another wrong-repository close; every bare-number heuristic (word lists) lost to a new spelling, so the rule became "no repository named, no close". A closed job is never reopened.

**How to apply:** carried P3s: mixed separators after "PR number" ("PR number: 12"), agentd.py:727 closed-count matches a title containing ": closed (", registry read failure is silent in agentd's log. New jobsparts module goes in ORDER of tests/test_jobs_parts.py. Plant mutations on LEFTOVER alternatives; each needs its own test row.

*Anchors: `tools/fabric/jobsparts/sweep.py::BARE_AFTER`, `tools/fabric/jobsparts/settle.py::_pr_state`*

*Observed 2026-10-16 (python-dev)*

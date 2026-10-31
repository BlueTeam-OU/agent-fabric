---
role: "python-dev"
class: solution
topic: "jobs-branch-evidence-258"
description: "fabric-jobs settles a contributor branch (done: on default branch; delivered: on origin); deliver on a done job appends evidence (#258)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0095287c8537d63
---

## fabric-jobs settles a contributor branch (done: on default branch; delivered: on origin); deliver on a done job appends evidence (#258)

#258 (2026-10-14): a job artifact that is a ref name (or origin/<ref>) is evidence: for `done` when its origin head is an ancestor of origin's default branch, for `delivered` when the remote (ls-remote, not the tracking ref) still has it. The default branch and HEAD are excluded by name (a fast-forwarded branch shares the default tip). Any landed evidence outweighs an un-folded branch (squash merges). `deliver <id> <artifact>` on a done job appends evidence, stamps `updated`, never reopens; dropped jobs take none.

**Why / how to apply:** run `deliver` BEFORE `done`: a done job with no artifact blocks `switch` (this session hit it for j113). A path-like word in an artifact now triggers a fetch (origin unreachable = unknown = refused). Tests: tests/test_jobs_switch.py, mutations on settle.py's three conditions.

*Anchors: `tools/fabric/jobsparts/settle.py::_branch_tips`, `tools/fabric/jobsparts/verbs.py::change`*

*Observed 2026-10-14 (python-dev)*

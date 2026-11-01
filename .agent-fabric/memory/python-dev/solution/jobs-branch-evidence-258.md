---
role: "python-dev"
class: solution
topic: "jobs-branch-evidence-258"
description: "fabric-jobs settles a contributor branch (done: on default branch; delivered: on origin); deliver on a done job appends evidence (#258)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0095287c8537d63
  - f59f644b17a1d050
---

## fabric-jobs settles a contributor branch (done: on default branch; delivered: on origin); deliver on a done job appends evidence (#258)

#258 (2026-10-14): a job artifact that is a ref name (or origin/<ref>) is evidence: for `done` when its origin head is an ancestor of origin's default branch, for `delivered` when the remote (ls-remote, not the tracking ref) still has it. The default branch and HEAD are excluded by name (a fast-forwarded branch shares the default tip). Any landed evidence outweighs an un-folded branch (squash merges). `deliver <id> <artifact>` on a done job appends evidence, stamps `updated`, never reopens; dropped jobs take none.

**Why / how to apply:** run `deliver` BEFORE `done`: a done job with no evidence blocks `switch` (this session hit it for j113). Work that leaves no artifact is closed with `done <id> --no-artifact "<what was done>"` (59f6be72, 2026-10-18): the reason is the evidence, but settle takes it only for a job that names no artifact at all (ac3f129a), never over a problem the artifacts raise. A path-like word in an artifact now triggers a fetch (origin unreachable = unknown = refused). Tests: tests/test_jobs_switch.py, mutations on settle.py's three conditions.

*Anchors: `tools/fabric/jobsparts/settle.py::_branch_tips`, `tools/fabric/jobsparts/verbs.py::change`*

*Observed 2026-10-20 (python-dev)*

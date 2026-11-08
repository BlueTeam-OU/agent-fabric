---
role: "python-dev"
class: solution
topic: "jobs-branch-evidence-258"
description: "un-folded branch artifact is excused only by a merged PR whose headRefOid is that branch's tip (PR 475, 2026-11-04); other landed evidence no longer settles it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bba80905331c3a69
  - e0095287c8537d63
  - f59f644b17a1d050
---

## un-folded branch artifact is excused only by a merged PR whose headRefOid is that branch's tip (PR 475, 2026-11-04); other landed evidence no longer settles it

The #258 line "any landed evidence outweighs an un-folded branch (squash merges)" is superseded by j202 / PR 475: `settle._landed` excuses an un-folded branch only when a merged PR the job names ended at that branch's tip (`headRefOid`); a folded sibling branch, a sha, a reply or a merged PR that ended at an older head leaves the branch unsettled. A head gh cannot read is "could not tell". `sweep.PrStates.head()` is the cached second lookup.

**Why:** the external review (F03) showed a delivered job naming one merged and one never-merged branch was swept to done.
**How to apply:** a fake gh for job tests must answer `headRefOid` beside `state` (tests/test_jobs_switch.py `heads=`, `head_fails=`); anchors `tools/fabric/jobsparts/settle.py::_landed`.

*Anchors: `tools/fabric/jobsparts/settle.py::_landed`, `tools/fabric/jobsparts/sweep.py::PrStates`*

*Observed 2026-11-04 (python-dev)*

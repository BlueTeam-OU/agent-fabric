---
role: "python-dev"
class: solution
topic: "j178-swept-branch-settle-merged-402"
description: "settle._pushed after a hygiene sweep (#402): head sources, merge-subject trace, carried gaps, post-review needs the verbatim report"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27d8ead0bf09e57b
---

## settle._pushed after a hygiene sweep (#402): head sources, merge-subject trace, carried gaps, post-review needs the verbatim report

#402 (merged 2026-10-27) made `settle._pushed` ask git from a worktree/working copy that exists and settle a paused job whose branch head is on origin/default: head = local branch, else origin tracking ref, else a "Merge pull request #N from o/<branch>" subject on default. `_peeled` uses show-ref so only exit 1 means absent.

**Why:** a swept merged branch left nothing else to find its head from; squash/ff-then-deleted-everywhere still refuses.
**How to apply:** carried P3: no test pins local-before-tracking-ref order; ADR-037 rule 10 line still says "its branch is pushed" (coordinator's). A branch with no commit of its own now settles (existing switch test commits first).

`fabric-pr post-review` refused my abridged copy of the reviewer's report as self-approval; the verbatim report written to a scratchpad file (not under an old name: `Write` refuses an existing unread file) posted fine.

*Anchors: `tools/fabric/jobsparts/settle.py::_peeled`, `tools/fabric/jobsparts/settle.py::_merged_by_subject`*

*Observed 2026-10-27 (python-dev)*

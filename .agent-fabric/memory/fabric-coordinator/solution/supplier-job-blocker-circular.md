---
role: "fabric-coordinator"
class: solution
topic: "supplier-job-blocker-circular"
description: "A REQUEST blocker on a supplier read 'answered; now waiting on job:<supplier>/jN' although jN showed delivered on the board; blockers.py says delivered clears it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e26255ba247b8825
---

## A REQUEST blocker on a supplier read 'answered; now waiting on job:<supplier>/jN' although jN showed delivered on the board; blockers.py says delivered clears it

j724, 2026-11-10: I blocked my job on `request:<id>` to devex-tooling, asking for a review fix on their `for/user/` branch. They replied and delivered (e3533104). Their job j316 then read `delivered`, and `fabric-jobs start j724` still refused: "answered; now waiting on job:devex-tooling/j316".

The docstring of blockers.py (line 25) says a `job:` blocker clears when that job is delivered, so this is either a defect or a timing gap: I read the board after the refusal, not before. Not reproduced. Meanwhile the commit hook refuses a git merge or push while the job is not active.

Workaround: `fabric-jobs block <id> "owner: <what was delivered, message id>"` (text with no checkable form replaces the blockers), then `fabric-jobs start <id>`.

Next time: run `fabric-jobs start` again after reading the board as delivered. If it still refuses, check_job's read of the peer's job-state is the defect. Related: [[own-job-blocker-never-clears]], [[peer-job-blocker-operator-only]].

*References: own-job-blocker-never-clears, peer-job-blocker-operator-only*

*Anchors: `tools/fabric/jobsparts/blockers.py::def check_job`*

*Observed 2026-11-10 (fabric-coordinator)*

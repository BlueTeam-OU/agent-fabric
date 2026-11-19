---
role: "fabric-coordinator"
class: workflow
topic: "switch-picks-job-landed-elsewhere"
description: "fabric-jobs switch can start a job whose work already landed in another job's PR; read origin/main for its artifact before working, and close it with done on that PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8afb253d370b2dd9
---

## fabric-jobs switch can start a job whose work already landed in another job's PR; read origin/main for its artifact before working, and close it with done on that PR

2026-11-10: after j724 merged as BlueTeam-OU/agent-fabric#545, `fabric-jobs switch` chose j719 ("fabric-pr has no disarm verb") and created a fresh worktree and branch for it. But devex-tooling's disarm verb had been folded into #545 and landed there: `git ls-tree origin/main tools/fabric/github/disarm.py` showed it on main.

So I closed j719 with `fabric-jobs done j719 BlueTeam-OU/agent-fabric#545`, removed the empty worktree and its branch, and switched by id to the job that was actually waiting (`fabric-jobs switch j741`).

Several jobs that record the same branch (j710, j719, j724 on one PR) all land when that PR merges. Close each of them on the PR right after the merge, before running switch. Related: [[next-work-rides-the-open-pr]].

*References: next-work-rides-the-open-pr*

*Anchors: `tools/fabric/jobsparts/settle.py::names the branch holding its work`*

*Observed 2026-11-10 (fabric-coordinator)*

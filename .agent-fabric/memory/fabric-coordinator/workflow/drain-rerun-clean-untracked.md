---
role: "fabric-coordinator"
class: workflow
topic: "drain-rerun-clean-untracked"
description: "re-running a drain pass: git restore leaves the last run's new files untracked; clean memory/ and .agent-fabric/ too, or MERGE TARGET AMBIGUOUS on a moved flat file"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 08c8ce1c73912cb3
---

## re-running a drain pass: git restore leaves the last run's new files untracked; clean memory/ and .agent-fabric/ too, or MERGE TARGET AMBIGUOUS on a moved flat file

2026-11-01, j511: a second pass-1 run after `git reset` refused edge-hosting with MERGE TARGET
AMBIGUOUS (rationale.md and rationale/rationale-carried-2026-10-18.md both present). `git restore
--source=origin/main --staged --worktree -- memory .agent-fabric` restores tracked paths only;
the previous run's new files (a flat file moved into its class directory) stay untracked.
**How to apply:** restore, then `git clean -fdq -- memory .agent-fabric`, before every re-run.
Related: [[drain-multi-pass-procedure]].

*References: drain-multi-pass-procedure*

*Observed 2026-11-01 (fabric-coordinator)*

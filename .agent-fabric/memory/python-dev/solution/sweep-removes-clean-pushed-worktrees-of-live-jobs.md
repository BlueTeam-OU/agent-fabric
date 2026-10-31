---
role: "python-dev"
class: solution
topic: "sweep-removes-clean-pushed-worktrees-of-live-jobs"
description: "fabric-branches --sweep (--all too) removed the worktree of an active job with an open PR; fixed in #364 to keep worktrees a live job names"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1d6c4f75e595a065
---

## fabric-branches --sweep (--all too) removed the worktree of an active job with an open PR; fixed in #364 to keep worktrees a live job names

Before #364 (merged 2026-10-24) `fabric-branches --sweep` removed any clean linked worktree whose commit was on a remote, including the worktree an active job's record named; the job then pointed at a missing path (j64). The disk broadcast of 2026-10-24 told every account to run `--sweep --all` and said it "keeps anything with commits off main", true for branches only. Nothing was lost: the branch was local and on origin; recovery is `git -C <clone> worktree add <job worktree path> <branch>` (`fabric-jobs show <job>` names both).

Now a queued, active, paused or blocked job's worktree is kept ("named by job jN (state)"); an unreadable job list, an unknown state or a non-path worktree keeps every worktree ("job list unreadable"). Open: its stderr line drops the cause (review F2 of #364); ADR-022 rule 11 and the branch-hygiene SKILL were to be amended by fabric-coordinator.

**Why:** a sweep read as "safe for my working copies" removes a job checkout you still push review fixes from.

**How to apply:** before relying on a sweep on a build that predates #364, check `git worktree list` afterwards; re-add the worktree rather than working from another checkout. Delivered jobs' worktrees are still removed by design. See [[security-boundary-arm-needs-architect-authorization]].

*References: security-boundary-arm-needs-architect-authorization*

*Anchors: `tools/fabric/branches.py::live_job_worktrees`*

*Observed 2026-10-24 (python-dev)*

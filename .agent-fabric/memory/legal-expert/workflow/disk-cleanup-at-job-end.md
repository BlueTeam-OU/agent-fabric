---
role: "legal-expert"
class: workflow
topic: "disk-cleanup-at-job-end"
description: "Before fabric-jobs switch, remove the job's worktree, sweep branches, clear scratch; say what and how much in evidence"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a7e2fb3d9c06a1ad
  - c2bf20ed17e06e9e
---

## Before fabric-jobs switch, remove the job's worktree, sweep branches, clear scratch; say what and how much in evidence

At the end of every job (done, delivered, dropped), before `fabric-jobs switch`:
1. Measure (`du -sh`).
2. `fabric-branches --sweep` in each working copy used. It removes only what is wholly on the default branch, and (verified on origin/main 2026-10-22) also this login's ended Claude Code sessions' scratch, so never `rm -rf` that scratch by hand; the classifier refuses it. It keeps a worktree a live job of this login names ("named by job jN"), and keeps every worktree when the job list is unreadable (verified on origin/main 2026-10-25, tools/fabric/branches.py live_job_worktrees); before that fix a sweep removed a live job's clean pushed worktree, restored with `git -C <clone> worktree add <job's worktree> <job's branch>`. It also keeps a session's scratch that a live process still uses, e.g. a /clear'ed session whose process writes under the old id (verified on origin/main 2026-10-31, branches.py, commit 84372f75); after a sweep, a watch whose output file is gone is armed again.
3. Whatever the sweep keeps, inspect yourself: `git -C <wt> status` and `git log --oneline <wt-HEAD> --not --remotes`. If it is clean and nothing is unpushed, `git worktree remove` it. Anything else: keep it or finish it.
4. Clear your own scratch, and run `podman system df` for anything the job started.
Put what was removed, and its size, in the job's evidence. Only this login's files.

**Why:** owner's word, relayed by fabric-coordinator broadcasts 01a150ca (2026-10-18) and 01a15576 (2026-10-19). A full /var/tmp crashed the fleet on 2026-10-17. On 2026-10-27, /home (shared by every account) was again at 97%, broadcast 01a17e45: the pressure recurs, so this is a standing step and not a one-off.

**How to apply:** a reflection job's worktree is the one most easily forgotten, because it produces no PR. The j7 worktree (21M) was found left behind on 2026-10-18.

*Anchors: `tools/fabric/branches.py::--sweep`*

*Observed 2026-10-22 (legal-expert)*

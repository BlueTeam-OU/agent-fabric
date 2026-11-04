---
role: "python-dev"
class: solution
topic: "watch-pins-modules-at-start-j162"
description: "gzcoord-inbox loads jobs/episodic/identity/workingcopy at start (pin_version, #366); late loads mix versions after an upgrade"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 54c63b97ef4f828c
---

## gzcoord-inbox loads jobs/episodic/identity/workingcopy at start (pin_version, #366); late loads mix versions after an upgrade

A watch outlives `fabric-ctl all upgrade fabric`; a module imported at the first delivery came from the new tree while the rest was old ("module 'jobs' has no attribute 'deliver_branch'"). Fixed in #366 by `inbox.pin_version()` (eager load at watch start), not by exit-and-re-run.

**Why:** runtime/identity.py execs tools/fabric/workingcopy.py from disk on every `resolve_context` (a loader, not an import), so pin_workingcopy memoises `jobs.identity._workingcopy`. runtime/identity.py itself is outside python-dev's entry. `gzmsg.whoami()` also re-runs identity per call (watch calls it only at start).

**How to apply:** a new late import or per-call exec on the delivery path needs a line in pin_version and a replaced-file case in test_gzcoord_intake. Also: `fabric-branches --sweep --all` removes a clean pushed worktree even of a live job; re-add with `git worktree add <path> <branch>`.

*Observed 2026-10-24 (python-dev)*

---
role: "fabric-coordinator"
class: workflow
topic: "merged-fix-not-active-until-upgrade"
description: a fix merged to main is not running for my own jobs until my control plane is upgraded — when distribution is refused, apply its behaviour by hand
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j524-docs-live-checks-moveto-terminal-reset"
derived_from:
  - c9fe80123397a8a4
---

## a fix merged to main is not running for my own jobs until my control plane is upgraded — when distribution is refused, apply its behaviour by hand

2026-11-05 (j618): #491 merged the re-point of an answered `request:` blocker to the job the request became.
Auto mode refused `fabric-ctl all upgrade fabric` as [Modify Shared Resources], so ~/projects/agent-fabric stayed
at 75f071d3, without #491. devex-tooling then answered my REQUEST 01a1ab6b with "taken, as my j293". On the old
code that REPLY would have cleared j618's blocker at the next ten-minute check: the very bug #491 fixed. I
re-pointed it by hand (`fabric-jobs block j618 --on job:devex-tooling/j293`).

**Why:** `fabric-jobs` runs from the control-plane checkout, not from the job's worktree. A merge reaches my
own tools only after the upgrade, and the upgrade is the owner's when auto mode refuses it.
**How to apply:** after a merge whose upgrade was refused, check `git -C ~/projects/agent-fabric log -1`
before relying on the new behaviour, and apply it by hand until the owner upgrades. Related:
[[auto-mode-refuses-account-assign]].

*References: auto-mode-refuses-account-assign*

*Anchors: `tools/fabric/jobsparts/blockers.py::now waiting on`*

*Observed 2026-11-05 (fabric-coordinator)*

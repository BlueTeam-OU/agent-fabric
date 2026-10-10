---
role: "fabric-coordinator"
class: workflow
topic: "own-account-upgrade"
description: "How the coordinator's own account gets the merged fabric — upgrade all refuses it off main; my agentd runs whatever this checkout has checked out"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4b75f8ae8c5c074d
---

## How the coordinator's own account gets the merged fabric — upgrade all refuses it off main; my agentd runs whatever this checkout has checked out

`fabric-ctl all upgrade fabric` refuses the coordinator's own account while
its checkout is on a feature branch ("not main; not moved"). My agentd runs
the code of whatever this checkout has checked out, and restarts by itself on
"source changed". So:
- on main: `git merge --ff-only origin/main` is the upgrade;
- on a local, unpushed branch: `git rebase origin/main` (fast-forwarding main
  alone leaves the agent on the branch's old base — seen 2026-10-09, "46 behind");
- on a pushed branch: merge origin/main into it, or switch to main.
Then read back with `fabric-ctl user fabric` — never a `fabric-ctl user upgrade
fabric` right after: it lands in the restart window, is lost, and fabric-ctl waits
out the 510 s budget (upgrade.mjs FABRIC_UPGRADE_BUDGET_S) before exiting 1.

*Observed 2026-10-09 (fabric-coordinator)*

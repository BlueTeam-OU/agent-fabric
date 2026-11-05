---
role: "fabric-coordinator"
class: solution
topic: "switch-repoints-blocked-job-branch"
description: "arm refused a PR because a blocked job from the previous session carried this branch — fabric-jobs switch re-pointed its branch/worktree fields"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d472a4215402c59f
---

## arm refused a PR because a blocked job from the previous session carried this branch — fabric-jobs switch re-pointed its branch/worktree fields

2026-11-01, #443 (j513): `fabric-pr arm 443` refused "job j511 on <j513 branch> is blocked — job:python-dev-04/j84".
j511 is #444's drain job, but `fabric-jobs show j511` listed branch and worktree as j513's: the switch
from j511 to j513 in that working copy re-pointed the blocked job's fields. Arm passed with
`--defer-job j511 "<it is #444's, the switch re-pointed it>"` and merged. Before arming after a switch,
read `fabric-jobs show` of every blocked job the arm names; a re-pointed one is a defer, not a blocker.
Seen again 2026-11-01 on main 00616fdf (after #438): the switch j410 → j449 gave j449 j511's branch and
worktree, though j449's work had landed as python-dev-02's #442 at 07:33Z; its read-back commit ab51a98b rode #444.
Twice now: a defect in fabric-jobs switch, my job j534.

*Observed 2026-11-01 (fabric-coordinator)*

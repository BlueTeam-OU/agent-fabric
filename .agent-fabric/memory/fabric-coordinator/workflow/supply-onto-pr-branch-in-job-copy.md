---
role: "fabric-coordinator"
class: workflow
topic: "supply-onto-pr-branch-in-job-copy"
description: "committing my part onto a contributor's PR branch under the job copy guard — check its branch out inside the job's own worktree, then switch back"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 03650c473e4efe90
  - c0918a3f3d93700d
---

## committing my part onto a contributor's PR branch under the job copy guard — check its branch out inside the job's own worktree, then switch back

j410 (2026-10-31): my ADR-037/ADR-022/skill commits for python-dev-01's #438 had to be made from inside
the job's copy, since the guard counts the session's cwd ([[guard-counts-session-cwd]]). What worked:
in the job worktree (clean, its own branch pushed), `git fetch origin <B>:refs/remotes/origin/<B>`,
`git switch -c <B> --track origin/<B>`, commit, `git push origin HEAD`, read back with ls-remote,
then `git switch` back to the job's branch. Then a REPLY to the contributor naming the shas and that
their review round covers the new head. j459 is the same shape next: python-dev-04's #439 (j76 clock
blocker) is open and invites my ADR-037 rule 8 + agent-jobs skill row (REPLY 01a18fe5).

j632 (2026-11-07): a second `git worktree add` for the branch is refused at commit (outside the job's
copy) — switch the job copy itself. And two such supplies the owner queues back to back are still
two sessions: after delivering one, `fabric-jobs start` of the next succeeds but its commit is
refused (ADR-037 rule 3); pause it, `fabric-jobs switch <id>`, `fabric-fresh --job <id>`.

*References: guard-counts-session-cwd*

*Observed 2026-11-07 (fabric-coordinator)*

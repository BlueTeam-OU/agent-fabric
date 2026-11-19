---
role: "fabric-coordinator"
class: workflow
topic: "supply-onto-pr-branch-in-job-copy"
description: "before fixing anything on a contributor's PR branch — never `git worktree add`; switch the job's own copy to the branch (refused at commit otherwise, hit twice: j632, j757)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 03650c473e4efe90
  - c0918a3f3d93700d
  - cbd11348019035ec
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

## before fixing anything on a contributor's PR branch — never `git worktree add`; switch the job's own copy to the branch (refused at commit otherwise, hit twice: j632, j757)

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

j757 (2026-11-10): did it again — built the #546 round-2 fix in a fresh worktree, the commit was
refused, and I moved it by `git diff > patch`, `git switch <B>` in the job copy, `git apply`. The
job copy's own branch being *ahead, unpushed* is no reason to avoid the switch: its commits stay on
its branch. A stale local copy of <B> already existing: `git switch <B> && git merge --ff-only origin/<B>`.

*References: guard-counts-session-cwd*

*Observed 2026-11-10 (fabric-coordinator)*

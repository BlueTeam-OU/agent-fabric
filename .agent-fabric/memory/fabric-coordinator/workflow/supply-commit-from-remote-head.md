---
role: "fabric-coordinator"
class: workflow
topic: "supply-commit-from-remote-head"
description: "supplying one commit onto another agent's PR branch when my local copy of it has drifted (an unpushed merge of main)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1d56ed980baf30ec
---

## supplying one commit onto another agent's PR branch when my local copy of it has drifted (an unpushed merge of main)

When my checkout of another agent's PR branch carries unpushed commits I do not
want to send (j634: a local merge of origin/main into python-dev-02's #504
branch), auto mode refuses `git reset --hard` to the remote head as
Irreversible Local Destruction. Instead: `git switch -c <scratch>
origin/<their-branch>`, commit there, `git push origin HEAD:<their-branch>`.
The drifted local branch stays as it was; sweep it later.

**Why:** the merge would have dragged main's commits into their branch's
history for no reason (#504 was already MERGEABLE); the reset was refused.

**How to apply:** before pushing onto someone's branch, compare
`git log origin/<branch>..HEAD`; push only what the job named. Related:
[[supply-onto-pr-branch-in-job-copy]].

*References: supply-onto-pr-branch-in-job-copy*

*Anchors: `policies/AUTHORITY.md::for/`*

*Observed 2026-11-07 (fabric-coordinator)*

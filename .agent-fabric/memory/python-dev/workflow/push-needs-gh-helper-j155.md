---
role: "python-dev"
class: workflow
topic: "push-needs-gh-helper-j155"
description: "Plain git push fails \"could not read Username\"; push through the gh credential helper; arm needs its own job in a fresh session"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0d9c4e33c2147552
---

## Plain git push fails "could not read Username"; push through the gh credential helper; arm needs its own job in a fresh session

j155: `git push` over https fails with "could not read Username" on this account; `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push origin HEAD` works.

**Why:** no helper is configured in the worktree; gh holds the token.
**How to apply:** push with that form. A session that worked a job cannot run `fabric-pr arm` for a later owner word ("arm 628") itself: add the arm job, `fabric-jobs switch`, run the printed fabric-fresh. See [[pristine-archive-excludes-j154]].

*References: pristine-archive-excludes-j154*

*Observed 2026-11-16 (python-dev)*

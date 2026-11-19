---
role: "legal-expert"
class: workflow
topic: "job-branch-feat-refused-use-for-user"
description: "In agent-fabric, the feat/ branch fabric-jobs gives a legal-expert job is refused by the commit hook; commit on <host>/<login>/for/user/<what>"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d37de8d2873fdcf1
---

## In agent-fabric, the feat/ branch fabric-jobs gives a legal-expert job is refused by the commit hook; commit on <host>/<login>/for/user/<what>

In agent-fabric, `fabric-jobs switch` puts a job on
`develop-qzapp/legal-expert-ee-eu/feat/<job>-…`, but the commit-msg hook
refuses any commit there for legal-expert: a contributor commits only on
`<host>/<login>/for/<caller>/<what>` (policies/authority.json). Seen on
j18, 2026-11-09 (the refused commit, then 8bbe03b6 on
`…/for/user/j18-privacy-notice-swiss`).

**Why:** the job branch name comes from fabric-jobs, and the contributor
fence comes from policies/AUTHORITY.md. The two disagree for a contributor role.

**How to apply:** before the first commit of a job here, run
`git checkout -b develop-qzapp/legal-expert-ee-eu/for/user/<what>`. Never
`git push origin HEAD:<for-branch>` after a refused commit: it pushes main's
head as the new branch.

*Anchors: `policies/authority.json::"role": "legal-expert"`*

*Observed 2026-11-09 (legal-expert)*

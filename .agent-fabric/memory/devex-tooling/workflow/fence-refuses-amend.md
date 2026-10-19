---
role: "devex-tooling"
class: workflow
topic: "fence-refuses-amend"
description: "the agent-fabric contributor fence refuses git commit --amend (no path staged); redo an unpushed commit with reset --soft HEAD~1 and a new commit"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 60e95da4904bde79
---

## the agent-fabric contributor fence refuses git commit --amend (no path staged); redo an unpushed commit with reset --soft HEAD~1 and a new commit

In agent-fabric, `git commit --amend` on a contributor branch is refused by the fence hook: "outside what devex-tooling commits here: (no path staged: an amend or an empty commit)" (seen 2026-10-14, j131, for/user/arm-codex-absent). To correct an unpushed commit's message, `git reset --soft HEAD~1` and commit again; the trailers (Kind, Fabric-Role) are stamped afresh. Never on a pushed commit someone may have folded.

*Anchors: `tools/fabric/guards/contributors.py::an amend or an empty commit`*

*Observed 2026-10-14 (devex-tooling)*

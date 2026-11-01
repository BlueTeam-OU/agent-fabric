---
role: "fabric-coordinator"
class: workflow
topic: "intake-project-is-senders"
description: "A REQUEST from another project's agent is queued under the sender's project, so switch makes a worktree there (InterWeave for j359, j360) even when the work is an agent-fabric commit"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d78dab2beb9af99
---

## A REQUEST from another project's agent is queued under the sender's project, so switch makes a worktree there (InterWeave for j359, j360) even when the work is an agent-fabric commit

2026-10-22: intake filed j359 (carrier ADR) and j360 (auto-mode entry for rust-services-dev's
s22_org_channels.py) under project `interweave`, because the senders wrote PROJECT: interweave.
`fabric-jobs switch` then made `InterWeave-j3NN-…` worktrees, but both artifacts are agent-fabric
files (`docs/adr/`, `policies/auto-mode.json`), committed on my one open PR (#356 at the time).
An empty misplaced worktree is safe to remove (check 0 commits off origin/main), but the job keeps
naming it and `switch` then refuses to leave a paused job; `block --on job:user/<next>` parks it.
In the fresh session, work in an agent-fabric worktree for such a job and ignore the InterWeave one.
Related: [[job-in-other-repo-needs-fresh-session]].

*References: job-in-other-repo-needs-fresh-session*

*Anchors: `tools/fabric/gzcoord/intake.py::PROJECT_SLUG`*

*Observed 2026-10-22 (fabric-coordinator)*

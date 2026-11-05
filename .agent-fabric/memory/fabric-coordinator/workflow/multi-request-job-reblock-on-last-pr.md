---
role: "fabric-coordinator"
class: workflow
topic: "multi-request-job-reblock-on-last-pr"
description: "a job blocked on several REQUESTs stays blocked after most merge; re-block on the last open PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6b0f616595e1dfad
---

## a job blocked on several REQUESTs stays blocked after most merge; re-block on the last open PR

j548 (2026-11-01) was blocked on four REQUESTs (audit contracts). Three landed as
merged PRs (#452, #453, #454) and were distributed (fleet at c7b41a90), yet all four
`request:` blockers still read waiting, because a request blocker clears on the
contract's REPLY, not on a merge. The job then woke a fresh session for nothing.

**Why:** "all must clear" over request blockers hides what is actually left.
**How to apply:** once the merges are checked (`gh pr list --state all`, `fabric-ctl all
status` fabric column), re-block with `fabric-jobs block <id> --on pr:<owner/repo>#<n>`
on the one PR still open, so the job wakes when it merges — then distribute. See
[[block-on-job-not-request-after-reply]], [[contract-job-block-on-builder-pr]].
Same read showed every account `managed DRIFTED` (see [[adr-043-managed-settings-option-1]]).

*References: adr-043-managed-settings-option-1, block-on-job-not-request-after-reply, contract-job-block-on-builder-pr*

*Anchors: `tools/fabric/jobs.py::request:`*

*Observed 2026-11-01 (fabric-coordinator)*

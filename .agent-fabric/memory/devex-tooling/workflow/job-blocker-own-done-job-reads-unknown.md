---
role: "devex-tooling"
class: workflow
topic: "job-blocker-own-done-job-reads-unknown"
description: "a job:<own login>/jN blocker shows \"unknown\", not cleared, even after jN is done — read fabric-jobs list --all yourself; to move umbrella → sub-job, block the umbrella on the sub-job, then switch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 205e4b58bf4743cb
---

## a job:<own login>/jN blocker shows "unknown", not cleared, even after jN is done — read fabric-jobs list --all yourself; to move umbrella → sub-job, block the umbrella on the sub-job, then switch

On 2026-10-24 j210 was blocked on `job:devex-tooling/j209`. j209 was `done`
(gzapi-org/agent-fabric-settings#9 merged), yet `fabric-jobs show j210`
still printed "job:devex-tooling/j209 unknown". The cause is in
tools/fabric/jobsparts/blockers.py: a job blocker is read through
`fabric-ctl <login> jobs`, a host operator's op. Any other caller gets
`unknown`, even for its own jobs. Confirm with `fabric-jobs list --all`.

To leave an umbrella job (j208) for its settings-repo sub-job (j210):
`fabric-jobs block j208 "<why>" --on job:<login>/j210`, then
`fabric-jobs switch j210`. switch refuses until this memory directory
has changed during the job being left. See [[settings-repo-job-needs-own-working-copy]]
and [[job-guard-judges-session-cwd]].

*References: job-guard-judges-session-cwd, settings-repo-job-needs-own-working-copy*

*Anchors: `tools/fabric/jobsparts/blockers.py::a host operator's op`*

*Observed 2026-10-24 (devex-tooling)*

---
role: "devex-tooling"
class: workflow
topic: "job-blocker-own-done-job-reads-unknown"
description: "a job:<login>/jN blocker (own or another login's) shows \"unknown\", never cleared — it never wakes the job; check the artifact on the remote yourself; to move umbrella → sub-job, block the umbrella on the sub-job, then switch"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 205e4b58bf4743cb
  - 503648f917750f8d
---

## a job:<login>/jN blocker (own or another login's) shows "unknown", never cleared — it never wakes the job; check the artifact on the remote yourself; to move umbrella → sub-job, block the umbrella on the sub-job, then switch

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

Another login's job reads the same way. j182 (InterWeave android check job
reads the Skia pin) was blocked on `job:p2p-network-dev-01/j94`. The pin
landed on InterWeave main (f42d88d1c), but the blocker stayed "unknown"
for two weeks, and the job only moved when architect-cto-01 chased it
(REQUEST 01a1aaa8, 2026-11-05).

**Why:** a job: blocker never clears for a non-operator caller, so it
never wakes the job.
**How to apply:** block on what is checkable on the forge (`pr:<owner/repo>#<n>`,
or a path to read on main) rather than `job:<other login>/jN`. When a
job: blocker is all there is, check the artifact on origin/main whenever
the job list shows it.

A free-text blocker never clears either. On 2026-11-07 a triage of the
blocked jobs found three of them stale. j183 had in fact been delivered
by me inside InterWeave #324 (3a093bfdb), but the job was never marked.
j198's PR (#374) had merged two weeks earlier. j80 was blocked in free
text on rust-ui-dev's E2eCase, which had been on main since #283
(2026-10-16). j80 was also filed under gzapp, because it predates the
move to InterWeave; `fabric-jobs project <id> interweave --working-copy ...`
re-points it. So whenever nothing is queued, check every blocked job
against the remote before ending idle.

*References: job-guard-judges-session-cwd, settings-repo-job-needs-own-working-copy*

*Anchors: `tools/fabric/jobsparts/blockers.py::a host operators op`*

*Observed 2026-11-07 (devex-tooling)*

---
role: "devex-tooling"
class: workflow
topic: "settings-repo-job-needs-own-working-copy"
description: "a REQUEST whose commits land in a settings repo is queued under agent-fabric; job-copy-guard refuses the commit — add a job per settings clone"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 736154ab6bc3f977
---

## a REQUEST whose commits land in a settings repo is queued under agent-fabric; job-copy-guard refuses the commit — add a job per settings clone

Intake queues a REQUEST by its PROJECT (agent-fabric), so a job whose
work is in BlueTeam-OU/ or gzapi-org/agent-fabric-settings gets the
agent-fabric clone as working copy, and runtime/claude-code/hooks/job-copy-guard.py
refuses `git commit` in the settings clone (ADR-037 rule 3). fabric-jobs
cannot re-point a job; `fabric-jobs add --working-copy <settings clone>`
one job per repo, block them, keep the umbrella for verify + reply.
Seen 2026-10-24, j208 -> j209/j210; reported to fabric-coordinator as
OBSERVATION 01a16ce1. Check the job's working copy before preparing edits.
`--working-copy` is the main settings clone even with my PR open there: `fabric-jobs switch` picks that open PR's
branch when it is addable and makes its worktree (tools/fabric/jobsparts/branching.py choose). A worktree path as
working copy is refused, and a delivered job's worktree is swept away by switch (j217 -> j218 -> j219, 2026-10-24).

*Observed 2026-10-24 (devex-tooling)*

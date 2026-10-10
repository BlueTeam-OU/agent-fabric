---
role: "fabric-coordinator"
class: workflow
topic: "bare-commands-not-sh"
description: "I run and name fabric commands by bare name (fabric-pr gate/arm/post-review/reply/wait-merged, fabric-query), never runtime/github/*.sh paths — in actions, messages and briefs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8d755468be51aa11
---

## I run and name fabric commands by bare name (fabric-pr gate/arm/post-review/reply/wait-merged, fabric-query), never runtime/github/*.sh paths — in actions, messages and briefs

Use `fabric-pr <verb>` (gate, review-status, post-review, reply, arm, sessions,
trial-merge, wait-merged, owed-supply, compliance) and `fabric-query`, never
`runtime/github/<x>.sh` or `tools/fabric/query.sh`, in commands I run, messages,
review briefs and dispatch prompts.

**Why:** the owner, 2026-10-09: "I still read too many .sh files here — these shims
should go out soon." The shim retirement (plan 2026-10-08, ADR-040 rule 7) stalled
after step 1 (#126); my own habit kept the paths alive (183 references on main).

**How to apply:** bare names everywhere; when a doc I touch names a shim path, fix it in
the same change. The retirement's steps 2–4 are tracked as a job.

*Observed 2026-10-09 (fabric-coordinator)*

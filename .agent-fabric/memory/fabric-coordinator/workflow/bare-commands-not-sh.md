---
role: "fabric-coordinator"
class: workflow
topic: "bare-commands-not-sh"
description: "I run and name fabric commands by bare name (fabric-pr gate/arm/post-review/reply/wait-merged, fabric-query), never runtime/github/*.sh paths — in actions, messages and briefs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 82d8398eccfe776b
  - 8d755468be51aa11
---

## I run and name fabric commands by bare name (fabric-pr verbs, fabric-query), never a script path

Use `fabric-pr <verb>` (gate, review-status, post-review, reply, arm, sessions, trial-merge, wait-merged, owed-supply, compliance) and `fabric-query`, in commands I run, messages, review briefs and dispatch prompts. The shim paths are gone from the tree: `runtime/github/*.sh` does not exist and `tools/fabric/query.sh` became `tools/fabric/query.py` behind `bin/fabric-query`. A bare name is therefore also the only form that still works, and the one that survives the next port.

**Why:** the owner, 2026-10-09: "I still read too many .sh files here — these shims should go out soon." My own habit had kept the shim paths alive (183 references on main); the retirement (ADR-040 rule 7) has since landed.

**How to apply:** bare names everywhere; when a doc I touch names a script path for a command that has a `bin/` name, fix it in the same change.

*Observed 2026-10-11 (fabric-coordinator)*

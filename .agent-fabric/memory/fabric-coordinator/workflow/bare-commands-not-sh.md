---
role: "fabric-coordinator"
class: workflow
topic: "bare-commands-not-sh"
description: "I run and name fabric commands by bare name (fabric-pr verbs, fabric-query), never a script path"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 82d8398eccfe776b
  - 8d755468be51aa11
  - e639ab1a204f6e5b
---

## I run and name fabric commands by bare name (fabric-pr verbs, fabric-query), never a script path

Use `fabric-pr <verb>` (gate, review-status, post-review, reply, arm, sessions, trial-merge, wait-merged,
owed-supply, compliance, counts) and `fabric-query`, in commands I run, messages, review briefs and dispatch
prompts. A bare name is the only form that survives the next port: the shell shims of these commands were
retired (ADR-040 rule 7), and `bin/` holds the names.

**Why:** the owner, 2026-10-09: "I still read too many .sh files here — these shims should go out soon." My own
habit had kept the shim paths alive.

**How to apply:** bare names everywhere; when a doc I touch names a script path for a command that has a `bin/`
name, fix it in the same change.

*Anchors: `bin/fabric-pr`, `bin/fabric-query`*

*Observed 2026-10-23 (fabric-coordinator)*

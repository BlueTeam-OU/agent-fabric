---
role: "devex-tooling"
class: workflow
topic: "agent-fabric-arm-json-outside-entry"
description: "projects/agent-fabric/integration/gh/arm.json is NOT in devex-tooling's authority entry (only gzapp's and interweave's are); and the fence refuses any non-for/ branch name"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5084c8e799c3c076
---

## projects/agent-fabric/integration/gh/arm.json is NOT in devex-tooling's authority entry (only gzapp's and interweave's are); and the fence refuses any non-for/ branch name

devex-tooling's entry in policies/authority.json lists projects/gzapp/integration/gh/ and projects/interweave/integration/gh/ only. agent-fabric's own arm.json (and the other projects' arm.json files) are outside it, even when a REQUEST says "your entry" (j143, REQUEST 01a14df6, 2026-10-18). Deliver that hunk as a diff ([[outside-entry-supply-as-staged-diff]]). Its body went inline in the REPLY (seq 306266) because no shared handover area could be found.

The contributor fence also refuses a commit on a branch that is not `<host>/devex-tooling/for/<caller>/<what>`. A job worktree that was made on `feat/...` must be renamed (`git branch -m`) before the first commit.

**Why:** both cost a refused commit in j143.
**How to apply:** before editing any arm.json, check the path against the entry. Confirm the branch is for/ before committing.

Related: arm_rules.py and arm_policy.py, split from arm.py, were outside the agent-fabric boundary until j143's diff. pr_gate and repo_policy are still unjudged.

*References: outside-entry-supply-as-staged-diff*

*Anchors: `policies/authority.json::projects/interweave/integration/gh/`*

*Observed 2026-10-18 (devex-tooling)*

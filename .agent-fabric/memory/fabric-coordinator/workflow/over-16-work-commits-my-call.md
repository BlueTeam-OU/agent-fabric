---
role: "fabric-coordinator"
class: workflow
topic: "over-16-work-commits-my-call"
description: "A PR past the 16-work-commit cap is mine to judge (arm as is, or split) — never asked of the owner"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7693b03ca6933d78
---

## A PR past the 16-work-commit cap is mine to judge (arm as is, or split) — never asked of the owner

Owner, 2026-10-22: when a PR of mine goes over 16 work commits, I decide by myself whether to arm it as it is or split it. Neither is always right; I am the judge, by evaluating. I had asked about #354 (21 work, 6 fix), and the answer was "arm as is" plus this rule.

**Why:** the cap is a charter line for the coordinator's own PRs; weighing it is part of the role, not an owner decision.

**How to apply:** weigh the re-review and churn a split costs against how reviewable the PR still is (one review covers it? the extra work was folded supplies or one coherent job?), decide, and write the reason in the arm basis ("over 16: armed as is because …" or the split's PR numbers). Better still, don't add a new job's commits to a PR already near 16. Related: [[no-8-commit-own-repos]], [[owner-arm-only-when-verified]].

*References: no-8-commit-own-repos, owner-arm-only-when-verified*

*Anchors: `tools/fabric/github/arm.py::smaller batches next time`*

*Observed 2026-10-22 (fabric-coordinator)*

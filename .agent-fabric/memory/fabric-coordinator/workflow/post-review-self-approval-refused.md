---
role: "fabric-coordinator"
class: workflow
topic: "post-review-self-approval-refused"
description: "2026-10-20: auto mode refused `fabric-pr post-review` of the review class's report on my own PR (gateway #75) as Self-Approval; posting falls to the owner until a policy says otherwise"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7e34a50eb64b80b3
---

## 2026-10-20: auto mode refused `fabric-pr post-review` of the review class's report on my own PR (gateway #75) as Self-Approval; posting falls to the owner until a policy says otherwise

2026-10-20, gateway #75 (j313): `fabric-pr post-review --repo BlueTeam-OU/agent-fabric-gateway 75 --model fable < report`
was refused by the auto-mode classifier as [Self-Approval], although the report is the code-review class's blind
review, not mine. Earlier PRs of mine were posted the same way without a refusal.

**Why:** the classifier reads posting a review on the poster's own PR as approving its own work.

**How to apply:** do not retry or route around it; hand the owner the one-line post command (a script under the
scratchpad if long), and propose a `policies/auto-mode.json` entry naming the review class's report as the
reviewed artefact. Related: [[post-review-own-pr-only]], [[auto-mode-refuses-account-assign]].

*References: auto-mode-refuses-account-assign, post-review-own-pr-only*

*Observed 2026-10-20 (fabric-coordinator)*

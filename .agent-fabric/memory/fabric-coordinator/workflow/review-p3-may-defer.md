---
role: "fabric-coordinator"
class: workflow
topic: "review-p3-may-defer"
description: "Fix P1/P2 in the PR, carry P3; post the final review with fabric-pr post-review naming the deferred P3s"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 58682253be73be78
  - fc334450f0d9b3b4
---

## Fix P1/P2 in the PR, carry P3; post the final review with fabric-pr post-review naming the deferred P3s

A PR's blind-review loop ends when no P1/P2 is open. Each remaining P3 is named in the final posted review and carried into the next PR (listed where the next branch's work is queued), not answered with yet another fix round; five rounds where each P3 fix drew a new P3 is the failure this rule prevents (owner, 2026-09-27).

**How to apply:** fix P1/P2, re-review that range, post the final review with `fabric-pr post-review` naming the deferred P3s, then read the gate with `fabric-pr gate`. See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-10-10 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: workflow
topic: "review-p3-may-defer"
description: P1/P2 review findings are fixed in the PR; a P3 may be carried to a later PR instead of another fix round
tier: 1
knowledge_scope: full
distilled_at: "2026-09-27"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc334450f0d9b3b4
---

## P1/P2 review findings are fixed in the PR; a P3 may be carried to a later PR instead of another fix round

The owner, 2026-09-27 on agent-fabric #51: "p2 should be addressed but p3
can be put eventually in a later pr". A PR's blind-review loop ends when no
P1/P2 is open; each remaining P3 is named in the final posted review and
carried into the next PR (listed where the next branch's work is queued,
[[next-fabric-branch-queue]]), not answered with yet another fix round.

**Why:** #51 ran five review rounds; the last three each fixed P3s and
each fix drew a new P3 — wording chasing wording.

**How to apply:** fix P1/P2, re-review that range, post the final review
with post-review.sh naming the deferred P3s, then read the gate. See
[[blind-review-loop]].

*References: blind-review-loop, next-fabric-branch-queue*

*Observed 2026-09-27 (fabric-coordinator)*

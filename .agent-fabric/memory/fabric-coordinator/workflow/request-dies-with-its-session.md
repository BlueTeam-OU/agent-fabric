---
role: "fabric-coordinator"
class: workflow
topic: "request-dies-with-its-session"
description: A REQUEST to one login is queued on its job list, so a deferred assignment survives; intake is best effort
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 1d7f19806d7eab1d
  - 8aad1b76c4e462ab
  - 8f78b04d9a4d1b10
---

## A REQUEST to one login is queued on its job list, so a deferred assignment survives; intake is best effort

A REQUEST addressed to one login becomes a queued job on that login's list (ADR-037 §5 rule 11): the receiving inbox adds it (`queue_received`) and `gzcoord-send` asks the control plane's `jobs-add` when the host operator sends (`queue_for_addressee`), both best effort and deduplicated by MESSAGE-ID (tools/fabric/gzcoord/intake.py). A deferred assignment therefore outlives its session on the list.

What intake misses still dies with the session: a TO-ROLE or BROADCAST message is never queued, and the relay's cursor has moved past anything a session received. So treat a deferred assignment as outstanding until the artifact exists, not until it is acknowledged; check the addressee's session (`fabric-ctl <login> presence`; `gzcoord-send` checks it and refuses without `--force`) and re-send with what CHANGED, not the same text. A re-send with new facts is information; the same text is nagging. See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-10-10 (fabric-coordinator)*

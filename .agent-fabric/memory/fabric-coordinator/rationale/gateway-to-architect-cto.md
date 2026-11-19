---
role: "fabric-coordinator"
class: rationale
topic: "gateway-to-architect-cto"
description: "owner 2026-11-14: transfer the gateway repo's ownership to architect-cto — project truth moves; .agent-fabric/ stays the coordinator's; job j861"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 456c1ac2c5255020
---

## owner 2026-11-14: transfer the gateway repo's ownership to architect-cto — project truth moves; .agent-fabric/ stays the coordinator's; job j861

On 2026-11-14 the owner said in my session: "also transfer the ownership of gateway repo to architect-cto". It is agent-fabric-gateway. The owner had put the whole repository under fabric-coordinator on 2026-09-24, as the fabric's own data plane. I read the request as role ownership, not a GitHub transfer.

What moves: the decision records, contracts, roadmap, CI and operating files. These are the gateway's project truth, and they now go to architect-cto. `.agent-fabric/` (taxonomy, remits) stays mine, as in every project.

Places to change, all in job j861:
- the gateway's taxonomy and remits
- the client settings repository's arming authority for the gateway
- policies/auto-mode.json, the arming-authority line. Editing it counts as Self-Modification, so the owner approves it.
- my charter's "the fabric's own data plane is the case"

The open gateway jobs (j834 ADR-007 enforcement, j844, j845, j854) go to architect-cto-01 by REQUEST. Read the current holder from the records, never from this note ([[repo-ownership-from-records]]).

*References: repo-ownership-from-records*

*Observed 2026-11-14 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: rationale
topic: "agent-repo-per-agent"
description: "Owner 2026-10-13 — each agent's secrets and settings share one repo, fabric-agent-<uuid>, in BlueTeam-OU; description names host/login/role, never the uuid; jobs/plans are working state backed up via Proton Drive CLI (separate); I run the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 39f92d2fb6d14d58
---

## Owner 2026-10-13 — each agent's secrets and settings share one repo, fabric-agent-<uuid>, in BlueTeam-OU; description names host/login/role, never the uuid; jobs/plans are working state backed up via Proton Drive CLI (separate); I run the transfers

The owner, 2026-10-13, in the coordinator's session (my split proposal declined):

1. One repository per agent holds both its encrypted secrets (ADR-038's pass store) and its
   **settings**, named `fabric-agent-<agent id>` (the UUIDv7 of ADR-039 stays in the name, so a login
   rename touches nothing). The GitHub description/topics carry `<host>/<login>` and the role — not
   the UUID, "is already in repo name".
2. **Settings only**: what configures the agent (binding, its own model layer…). Jobs, plans, notes
   are current working state, not settings: they get a **backup**, by the Proton Drive CLI — a
   separate issue.
3. The ~27 `agent-fabric-secrets-<id>` repos move from gzapi-org to **BlueTeam-OU**; the owner said
   I do the transfers ("you have already done it for other repo in past").

**Why:** one place per agent (back up, move host, retire = one repo), access already per login.
**How to apply:** amend ADR-038/039 first; tooling accepts both names; then transfer+rename; then the
settings checkpoint. Related: [[repo-transfer-owner-hand]] (the classifier refused me once; the
owner's word here is explicit).

*References: repo-transfer-owner-hand*

*Observed 2026-10-13 (fabric-coordinator)*

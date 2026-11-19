---
role: "fabric-coordinator"
class: rationale
topic: "gateway-arming-matches-interweave"
description: "owner 2026-11-14: agent-fabric-gateway's arming settings match InterWeave — architect-cto for both authorities, authority_own_prs false; j861's settings change had never landed"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f4e5d32564ed8110
---

## owner 2026-11-14: agent-fabric-gateway's arming settings match InterWeave — architect-cto for both authorities, authority_own_prs false; j861's settings change had never landed

On 2026-11-14 the owner answered in my session: the gateway's arming settings should match InterWeave's. The file is BlueTeam-OU/agent-fabric-settings repos/agent-fabric-gateway.json, and the values are:
- commits.boundary_authority: architect-cto
- commits.below_min_authority: architect-cto
- commits.authority_own_prs: false, so the owner arms architect-cto's own PRs

This was found during the review of BlueTeam-OU/agent-fabric#600. j861's job title listed this settings change, but no settings PR was ever made. On main the file still said fabric-coordinator, with authority_own_prs true.

devex-tooling owns that repository and was sent the REQUEST. Before claiming that a settings change has landed, read the file on the settings repository's main ([[accepted-only-when-on-main]]).

*References: accepted-only-when-on-main*

*Observed 2026-11-14 (fabric-coordinator)*

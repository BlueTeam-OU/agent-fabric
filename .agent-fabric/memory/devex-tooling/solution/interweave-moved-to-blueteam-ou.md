---
role: "devex-tooling"
class: solution
topic: "interweave-moved-to-blueteam-ou"
description: "InterWeave lives at BlueTeam-OU since 2026-10-12, client blueteam; gh API writes through gzapi-org/InterWeave fail with HTTP 307"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6a608ac7be94d4be
---

## InterWeave lives at BlueTeam-OU since 2026-10-12, client blueteam; gh API writes through gzapi-org/InterWeave fail with HTTP 307

On 2026-10-12, on the owner's word, devex-tooling transferred gzapi-org/InterWeave to
BlueTeam-OU (gh api POST repos/<old>/transfer new_owner=…; it answers at the new name
within seconds). The owner also moved its client from gzapi to blueteam.

- Carried over intact: the repo-level ruleset "main protection" (merge queue, required
  checks; compared against a JSON snapshot taken before), open PRs, Actions settings,
  merge settings. Org-level rulesets and org secrets would NOT carry over — check
  `repos/<r>/rulesets` source and `actions/organization-secrets` before any transfer.
- Its arming policy moves from gzapi-org/agent-fabric-settings to BlueTeam-OU's
  (branches feat/interweave-to-blueteam in both). The settings CI pins
  AGENT_FABRIC_REF, so each PR bumps the pin to the registry commit naming the new client.
- Git follows the redirect; API writes need GH_REPO=BlueTeam-OU/InterWeave until a clone's
  origin is re-pointed (same as the agent-fabric move, [[agent-fabric-moved-to-blueteam-ou]]).
- InterWeave's check_spike_locks.sh `ours()` matched gzapi-org/interweave only (j106). PR #274
  anchors it at both ends: github.com via https/ssh://git@/git@, either org, interweave(.git)/"
  -- no left anchor had let not-blueteam-ou/, xgzapi-org/, other hosts and InterWeave.rs in.
- fabric-pr arm compares a WAIVES line's repo with GH_REPO or origin (gh.this_repo), so a clone
  still on the gzapi-org origin waives with the old org; CLAUDE.md said gzapi-org (fixed in #274).
- Still open: InterWeave workspace Cargo.toml `repository` names gzapi-org (p2p-network-dev's,
  OBSERVATION 01a1330e sent to p2p-network-dev-01).

*References: agent-fabric-moved-to-blueteam-ou*

*Observed 2026-10-12 (devex-tooling)*

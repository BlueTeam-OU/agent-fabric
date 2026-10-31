---
role: "rust-services-dev"
class: solution
topic: "gateway-body-user-id-passthrough"
description: "what end-user identifiers Claude Code and Codex send through the gateway, and the decided forward/drop/hash rule for metadata.user_id (ADR-003 rule 17)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 904d14ca06b824e3
---

## what end-user identifiers Claude Code and Codex send through the gateway, and the decided forward/drop/hash rule for metadata.user_id (ADR-003 rule 17)

The gateway forwards the body byte for byte except the `model` token (crates/protocol/core/src/selector.rs) and strips only hop-by-hop and credential headers (crates/backend/http/src/client.rs), so client identifiers reach the upstream as sent (main 86a1316, 2026-10-19).

Measured by shape on 2026-10-19 (spikes/user-id-shape; live-check record architecture/research/live-checks/2026-10-19-end-user-identifiers-by-shape.md, branch develop-qzapp/rust-services-dev-01/feat/j48-j288-metadata-user-id-through-the at 217cf79):
- Claude Code 2.1.286, API-key mode: metadata.user_id is a JSON string {device_id: 64 hex, stable per config dir; account_uuid: empty, even with a stored oauthAccount; session_id: UUID per session, equal to the x-claude-code-session-id header}.
- Codex 0.162.1 sends no metadata/user/safety_identifier. Its client_metadata and x-codex-turn-metadata carry a stable installation id and the workspace's git remote URL and latest commit.

The decision is fabric-coordinator's (j288). The draft (architecture/adr/drafts/ADR-003-end-user-identifier.md) recommends a shape-preserving HMAC of device_id, declared per backend, gated on live checks. Each login has its own OpenRouter key (agent-fabric ADR-012 rule 4), so "logins share one key" is wrong.

Decided 2026-10-19 (fabric-coordinator DECISION 01a155dd, owner): option C, ADR-003 rule 17. A backend declares forward (default), drop or hash. The key is per login and subscription account, carried on the token file's second line (64 lowercase hex) so one read gives both; env profiles use a second variable (pseudonym_key_name). Built in gateway PR #72, merged 2026-10-20 at 7dec78ff, with fabric-coordinator's plan-v1 schema/README/contract §10 supply (8437c6f). Rule 17's evidence gate binds route declarations, not the merge: nothing may declare drop or hash until the two live checks are recorded (spikes/user-id-live/check.py, still not run on 2026-10-20; the operator runs it with 0600 credential files).

*Observed 2026-10-20 (rust-services-dev)*

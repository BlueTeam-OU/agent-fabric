---
role: "fabric-coordinator"
class: domain
topic: "tool-litellm"
description: "LiteLLM (BerriAI, MIT) reviewed 2026-11-13 at v1.110.0rc1, its move to Rust: still a multi-tenant product gateway (Postgres, Redis, virtual keys), not our gateway's shape or a dependency; borrow differential testing for ports and the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc57fbf131d30c67
---

## LiteLLM (BerriAI, MIT) reviewed 2026-11-13 at v1.110.0rc1, its move to Rust: still a multi-tenant product gateway (Postgres, Redis, virtual keys), not our gateway's shape or a dependency; borrow differential testing for ports and the stall-is-a-failure stream rule

https://docs.litellm.ai, read 2026-11-13 (release notes v1.103–v1.110.0rc1, /rust-migration, blogs
"Routing in Rust" 11-11 and "/v1/messages end-to-end in Rust by Dec 1" 10-26, the Claude subscription
tutorial). Docs only, nothing run. First review on record: before, only a passing mention in [[pr-agent]].

**The change:** v1.110.0rc1 (11-11) deletes the Python router (~50k lines); retries, fallbacks, cooldowns and
deployment selection run in one Rust core behind a thin Python API (registry/settings/health/select/apply). A config
the Rust core declines stops the proxy at startup; `LITELLM_RUST` no longer chooses. Next: an Axum server in front of
every request by 2026-12-01, a Rust fast path for `/v1/messages` (Anthropic on Anthropic/Bedrock/Vertex, simple-shuffle,
supported callbacks only) and the rest forwarded to Python workers on the same host. Self-scored 39% of "major APIs"
(57.4/146 points). Forwarding-only bench (July): p99 +0.7 ms, 21.8 MB, against 257.7 ms / 329.5 MB for Python v1.
Cadence: several releases a week, LTS line 1.108.x.

**Against agent-fabric-gateway** (Rust, one per harness session, loopback, no persistence, plan from the control
plane, 0.3.0): LiteLLM is still a tenant product: Postgres and Redis on the path, virtual keys, budgets at list
price, spend ledger, dashboard, MCP and skills hubs. Its Rust front with a fallback to Python is a migration seam, not
our split. Same verdict as [[otari]]: no adoption, no dependency.

**Worth taking:**
- Differential testing for a port: run the same case through old and new core, normalise ids and times, compare
  client response, provider requests, DB/Redis writes, callbacks, router state; one extra lane of the old build
  measures noise. Refactor-to-new-API first, then swap, each step with its own diff test. Our Bash→Python waves used a
  Node/bash oracle per suite ([[node-oracle-not-current-text]]); a lane-against-itself noise control is the missing piece.
- A stream that stalls, aborts or ends without a finish reason is a failure (v1.109), so retry/fallback apply. A check
  for our gateway's bounds (contract §§16–17).
- Subscription forwarding: Claude Code's OAuth token in `Authorization` is forwarded to direct `anthropic/`
  deployments ahead of configured keys, beta header added; `count_tokens` and the `/anthropic` pass-through use the
  proxy's own key; spend rows say `used_client_oauth_token`. Our gateway holds credentials only by plan name; keep it.
- A 404 on a lookup must not cool down a healthy deployment (v1.110 fix): a reason class, not every error, trips a
  cooldown. Matches our exhausted/transient_429 split.

**Code reuse (checked 11-13):** LICENSE is MIT for everything outside `litellm/enterprise/` (own LICENSE.md);
`litellm/rust/` (Cargo workspace, edition 2024, 80 crates, 1052 .rs files) says `license = "MIT"`. Into the
Apache-2.0 gateway only with the MIT notice kept (REUSE annotation for the copied paths). Self-contained candidates:
`framer` (SSE + AWS event-stream framing, 31 KB, tests), `circuit-breaker` (zero deps, 22 KB). Not `router-core`
(627 KB, pulls their cache and types). Gateway code is rust-services-dev's lane, not mine.

*Anchors:* agent-fabric-gateway:README.md::Rust data-plane gateway

*References: node-oracle-not-current-text, otari, pr-agent*

*Observed 2026-11-13 (fabric-coordinator)*

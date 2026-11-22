---
role: "fabric-coordinator"
class: domain
topic: otari
description: "mozilla-ai/otari (Apache-2.0, Python/FastAPI multi-tenant LLM gateway, 0.28, many releases a week, AI-built at high churn): not our gateway's shape or a dependency; its hybrid mode confirms our control/data split; borrow ordered attempts…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9b920c2fbc1cd597
---

## mozilla-ai/otari (Apache-2.0, Python/FastAPI multi-tenant LLM gateway, 0.28, many releases a week, AI-built at high churn): not our gateway's shape or a dependency; its hybrid mode confirms our control/data split; borrow ordered attempts, full-vs-broke spill-over, absorbed usage rows, error-body redaction, the Messages↔Responses bridge rules, an A/B load gate

https://github.com/mozilla-ai/otari, read 2026-10-19 from a shallow clone (code and docs; nothing
run). 0.1.0 2026-06-25 → 0.28.0 2026-10-16, about 140k lines of Python in src/, 108 alembic
migrations, 41 CI workflows, commits co-authored by Claude. Open-core (otari.ai overlay through
Null-Object ports: Billing, Entitlement, Growth). One Python monolith + Postgres (+ Redis for
cross-replica rate limits); `any-llm-sdk[all]` for 40+ providers, translation, budgets, virtual
keys, a dashboard, and MCP/web-search/fetch/code-exec tool loops.

**Against agent-fabric-gateway** (Rust, per-session child of the launcher, loopback, no
persistence, raw/surgical passthrough, plan from the control plane, usage from rate-limit
headers): otari is a product gateway for tenants. Ours is a data plane for one harness session.
Its hybrid mode (data plane only, `POST /gateway/provider-keys/resolve` returns an ordered
`attempts[]` of provider, model, key, base; "makes zero routing decisions of its own") is our
gateway ADR-001 split, reached independently: evidence that the split is right.

**Why it matters:** the gateway's open items (plan-ordered alternatives, ADR-006 rule 13; the
Stage 9 Anthropic↔Responses bridge, ADR-010; Stage 11 performance and metrics; withholding of
echoed credentials that is verbatim and head-only) all have a worked, tested version in otari.

**How to apply (each checked in its source):**
- Alternatives: a plan entry as an ordered attempts list; fail over only before the first
  byte (otari holds the first chunk up to `streaming_first_chunk_hold_ms`, default 15 s,
  docs/routing.md:351-358; ours commits on the first byte, so same rule, no hold). Inside a
  fallback chain set SDK retries to 0, so only one layer retries (docs/configuration.md:403-438).
  Keep ours (one retry, only after a credential swap) and ADR-055's control-plane retries from
  stacking.
- "Full" versus "broke": candidates skip a model whose per-model limit is full without calling
  it; `on_failure` handles errors. Maps to our usage map's `exhausted` versus `transient_429`
  and ADR-052's account switch.
- One request, many attempts: failed attempts are `absorbed` usage rows under one
  `request_group_id` (src/gateway/models/usage.py), plus response headers for attempt count,
  fallback, provider and model. A shape for our structured events and the dispatch ledger.
- Redaction by pattern of provider error bodies (bearer, sk-/gsk_/xai- keys, AIza, `api_key=`,
  account ids, ARNs, URLs; capped at 400 chars; services/upstream_redaction.py). Closes our
  "verbatim, head-only" known issue.
- Bridge rules (services/inference/_messages_responses_bridge.py): encrypted reasoning carried
  in signed thinking blocks, `store:false`, stateful fields (`previous_response_id`,
  `conversation`, hosted tools) refused with 400 rather than faked.
- The provider SDK's own environment variable (OPENAI_API_KEY) is never a credential
  (src/gateway/AGENTS.md:259-268). Ours already holds credentials only by plan name; keep it.
- An HMAC of the end-user id goes upstream, never the raw tag. Worth asking whether our
  passthrough forwards a login in `metadata.user_id`.
- Load gate: base and head images A/B against a fake provider (50 ms), CPU pinned, open-loop
  1000 rpm, fails on a p50 regression (loadtest/). For Stage 11.
- `routing explain`: a pure routing compiler, so explaining a plan needs no I/O. A sibling for
  our `validate-plan`.

**Not adopted:** the Python stack and `any-llm[all]` weight, the DB, the open-core seams, the
models.dev catalog fetch on by default every 24 h (config.py:1151), the ChatGPT-subscription
path through a third-party OAuth proxy, and a 7k-line `_pipeline.py` with churn of many
releases a week. Related: [[trust-philosophy-uniform]] (otari fences tenants, not kinds of
actor), [[claudemanager]] (rate-limit header ingestion).

*References: claudemanager, trust-philosophy-uniform*

*Observed 2026-10-19 (fabric-coordinator)*

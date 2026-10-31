---
role: "devex-tooling"
class: domain
topic: "subagent-transcript-shape"
description: "what a Claude Code subagent transcript shows about how the run ended, cost and effort (read 2026-10-14 over 348 transcripts on develop-qzapp)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f22bc25d50c273a8
---

## what a Claude Code subagent transcript shows about how the run ended, cost and effort (read 2026-10-14 over 348 transcripts on develop-qzapp)

Claude Code subagent transcripts (`~/.claude/projects/<proj>/<session>/subagents/agent-<id>.jsonl` + sibling `.meta.json` with agentType, description, toolUseId), read 2026-10-14 over 348 runs:
- One assistant record per content block, each repeating the message's usage; intermediate ones have stop_reason null, only the last carries the final output_tokens and the real stop_reason.
- Review-class runs mostly end with a `SubagentHandback` tool_use followed by a user tool_result `{"success":true,...}` — a completed run whose last record is a tool_result, not an end_turn.
- API errors are assistant records with `isApiErrorMessage: true`, model `<synthetic>`, top-level `error` (rate_limit, server_error, unknown).
- A user interrupt is a user text starting `[Request interrupted`.
- Records carry a top-level `effort` string; usage may carry `output_tokens_details.thinking_tokens`; broker model ids are `vendor/model` (e.g. anthropic/claude-opus-5).
- SubagentStop hook input: effort is documented as an object `{level}`; the docs name no status, stop-reason or cancellation field, so how a run ended is read from the transcript only. Used by runtime/claude-code/hooks/subagent-ledger.py (j125).
- SubagentStop timing (probed 2026-10-15, j132, CC 2.1.286, fg + bg Explore via `claude -p --settings` with a polling probe hook): the hook fires when the subagent calls SubagentHandback; at entry every assistant message is on disk but the hand-back's tool_result is not — it lands ~0.5 s later while the hook runs. Records reach the file after their own timestamp. A script summing usage per assistant *record* overcounts ~1.6–1.9× (turns, cache) — the source of OBSERVATION 01a13c97's "11 of 19 turns" (confirmed by its sender, REPLY 01a13e33: 19 records = 11 message ids, row exact; the review-economics report's absolutes were per-record, median 1.80 records/message over 593 review transcripts); count distinct message ids.

*Observed 2026-10-15 (devex-tooling)*

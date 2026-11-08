---
role: "rust-services-dev"
class: domain
topic: "claude-code-print-session-channel-facts"
description: "Claude Code 2.1.286 -p sessions with a channel: a mid-user-turn event waited (one run), mid-event-turn events joined (one burst), closed stdin still answers, which permission modes deny reply, host prompts need --permission-prompt-tool…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 0e0d46f5f9ad95ad
  - b6f86d508c28a754
---

## Claude Code 2.1.286 -p sessions with a channel: a mid-user-turn event waited (one run), mid-event-turn events joined (one burst), closed stdin still answers, which permission modes deny reply, host prompts need --permission-prompt-tool stdio, channelsEnabled by login kind

Measured on Claude Code 2.1.286, 2026-10-24 (InterWeave SPIKE-001 S25, `spikes/spike-001/runs/s25-*`, PR #427):

- In S25's one run (fact 45, stdin open), a channel notification arriving during a `-p` stream-json USER turn was not injected into it: it became a separate user message once the turn ended and started a turn of its own. In S29's one burst (fact 74), events arriving during a turn an event had started joined that turn. Whether the kind of turn decides is not established; neither is a rule.
- Closing stdin mid-turn: the process finishes the turn, runs the turn the queued event starts, then exits 0 with no signal.
- In `-p`, `--channels` for a plugin not on any allowlist logs nothing anywhere (debug, stderr, stdout). An interactive session logs a refusal.
- `--permission-mode manual` shows as `permissionMode: "default"` in init. An MCP tool not in `--allowedTools` is denied: a `system`/`permission_denied` line, then `permission_denials` in the result. No `control_request` reaches the stream-json host, even with `--permission-prompts host` (the default) — unless `--permission-prompt-tool stdio` is also passed (S26, 2026-11-03): then a `can_use_tool` control_request arrives on stdout, answered with `{"type":"control_response","response":{"subtype":"success","request_id":…,"response":{"behavior":"allow","updatedInput":<input>}}}` or `behavior: deny` + `message`.
- Without `--allowedTools`, `reply` is denied in acceptEdits, dontAsk, plan, manual and `--permission-prompts none`; it goes through in `bypassPermissions` (no extra flag needed) and `auto` (S26, PR #531).
- `channelsEnabled` is ignored for a claude.ai env-token login; an API-key login (even a placeholder key) is refused "channels not enabled by org policy (set channelsEnabled: true in managed settings)" unless it is `true`. `channel_enable` answers the gate's verdict with no model call (S27).
- `claude plugin configure <id>` only lists the options, with or without a terminal. Only `--values-stdin` with a JSON object writes `pluginConfigs`.
- `--include-partial-messages` gives `stream_event` text deltas, so a driver can act "mid-answer".
- S29 (2026-11-04, PR #555, facts 70-75):
  - `--allowedTools` lets `reply` through in `acceptEdits` and `dontAsk`, and never in `plan`.
  - A message that asks for an answer, after a first turn that said nothing about events, got `reply` in 1 of 3 runs. In the other two the model declined because the request "came from the channel".
  - The host reads a stdio line whole up to 8 MiB. The model's prompt is the real bound: "Prompt is too long" somewhere between 320 KiB and 1 MiB.
  - Events that arrive during an event's own turn join that turn as attachments; there is no pacing.
  - With no mode flag, the init reports `auto` on 2.1.286 and `default` on 2.1.311 and 2.1.317, with the same auto-mode gate line on all three. A 2.1.286 session that starts about 30 s late also reports `default`.

**Why:** these decide how a headless channel host must be built (keep the turn short, pass `--allowedTools`, check registration yourself).

**How to apply:** treat these as facts about 2.1.286 only, and re-measure on a newer build before relying on them. Related: [[spike-facts-cite-committed-runs]].

*References: spike-facts-cite-committed-runs*

*Observed 2026-11-04 (rust-services-dev)*

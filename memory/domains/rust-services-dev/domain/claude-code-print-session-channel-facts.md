---
role: "rust-services-dev"
class: domain
topic: "claude-code-print-session-channel-facts"
description: "Claude Code 2.1.286 -p sessions with a channel: mid-turn events queue, closed stdin still answers, manual mode denies MCP tools, plugin configure needs --values-stdin"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - b6f86d508c28a754
---

## Claude Code 2.1.286 -p sessions with a channel: mid-turn events queue, closed stdin still answers, manual mode denies MCP tools, plugin configure needs --values-stdin

Measured on Claude Code 2.1.286, 2026-10-24 (InterWeave SPIKE-001 S25, `spikes/spike-001/runs/s25-*`, PR #427):

- A channel notification arriving while a `-p` stream-json turn is running is not injected into that turn. It becomes a separate user message once the turn ends and starts a turn of its own.
- Closing stdin mid-turn: the process finishes the turn, runs the turn the queued event starts, then exits 0 with no signal.
- In `-p`, `--channels` for a plugin not on any allowlist logs nothing anywhere (debug, stderr, stdout). An interactive session logs a refusal.
- `--permission-mode manual` shows as `permissionMode: "default"` in init. An MCP tool not in `--allowedTools` is denied: a `system`/`permission_denied` line, then `permission_denials` in the result. No `control_request` reaches the stream-json host, even with `--permission-prompts host` (the default).
- `claude plugin configure <id>` only lists the options, with or without a terminal. Only `--values-stdin` with a JSON object writes `pluginConfigs`.
- `--include-partial-messages` gives `stream_event` text deltas, so a driver can act "mid-answer".

**Why:** these decide how a headless channel host must be built (keep the turn short, pass `--allowedTools`, check registration yourself).

**How to apply:** treat these as facts about 2.1.286 only, and re-measure on a newer build before relying on them. Related: [[spike-facts-cite-committed-runs]].

*References: spike-facts-cite-committed-runs*

*Observed 2026-10-24 (rust-services-dev)*

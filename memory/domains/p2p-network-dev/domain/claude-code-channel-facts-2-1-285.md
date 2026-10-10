---
role: "p2p-network-dev"
class: domain
topic: "claude-code-channel-facts-2-1-285"
description: "Measured Claude Code 2.1.285 channel behaviour (SPIKE-001, PR #172): handshake, enabling, rendering, escaping, tools, shutdown, crash; and how to drive a nested Claude session as evidence"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4b539f242e917f96
---

## Measured Claude Code 2.1.285 channel behaviour (SPIKE-001, PR #172): handshake, enabling, rendering, escaping, tools, shutdown, crash; and how to drive a nested Claude session as evidence

SPIKE-001 measured these against Claude Code 2.1.285 on 2026-10-03, with all runs redone from the committed tree after review (spikes/spike-001/README.md, PR #172, head 47bd7b3e):
- **Handshake:** a `server/discover` probe comes first. Answering -32601 falls back to `initialize` at 2025-11-25 ("legacy" era). `MCP_PROTOCOL_NEGOTIATION=legacy` skips the probe. Per the docs, a 2026-07-28-era server is not registered as a channel.
- **Enabling:**
  - Delivery happens only in an INTERACTIVE session.
  - `--dangerously-load-development-channels server:<name>` or `plugin:<name>@inline` (for a `--plugin-dir` plugin) shows a warning screen whose option 1 must be accepted.
  - `-p` never delivered at the three timings tried.
  - Without the flag the debug log says "skipped: not in --channels list".
- **Packaging:** plugin.json `"channels": [{"server": "<.mcp.json key>", "displayName": ...}]` passes `claude plugin validate --strict` only with `author`.
- **Rendering:**
  - `<channel source="<server name>" k="v"...>\nbody\n</channel>`, with the meta keys IN THE ORDER SENT, not sorted. An early run seemed to show sorting only because serde_json's default map sorts; `preserve_order` disproved it.
  - `meta.source` becomes a DUPLICATE `source` attribute.
  - Meta keys must match `^[a-zA-Z_][a-zA-Z0-9_]*$`; others are dropped and logged.
  - Meta values are XML-escaped. The body is escaped ONLY for `</channel>` (it becomes `<\/channel>`).
  - The instructions arrive as an `mcp_instructions_delta` attachment.
- **Tools:** MCP tools are deferred and loaded with ToolSearch. A `tools/call` carries `_meta.claudecode/toolUseId`.
- **Shutdown:** SIGINT, then SIGTERM about 100 ms later, then SIGKILL about 400 ms after that. stdin is never closed, so there is no graceful window.
- **Crash:** a crashed stdio server is not restarted and its tools vanish. The /mcp hint that appeared came from the model.

How to drive a nested session as evidence:
- Give the child an ALLOW-LISTED environment (HOME, PATH, locale, USER, SHELL, TMPDIR), not "strip CLAUDE*". Otherwise the parent's tokens, its fabric markers and its ANTHROPIC_DEFAULT_*_MODEL leak, and the last one changes the measured model (#172 review P2).
- Run from a scratch cwd with `--setting-sources local`. Account connectors still load.
- Use a pty for interactive runs. Match screen text with all whitespace removed.
- The session transcript at ~/.claude/projects/<cwd-slug>/*.jsonl holds the exact injected text.
- Write raw output OUTSIDE the tree from the start, and commit only a distillation.
- Make a test's input able to distinguish the hypotheses: sorted input cannot show sorting.

*Observed 2026-10-03 (p2p-network-dev)*

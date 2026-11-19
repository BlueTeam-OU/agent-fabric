---
role: "fabric-coordinator"
class: domain
topic: "claude-code-code-mode-2-1-322"
description: "CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1 already exists in the pinned 2.1.322 (\"Code Mode (experimental)\"); headless read-back 2026-11-16: no new tool, WebFetch dropped, ~3k fewer prompt tokens"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 80a8980569349c99
---

## CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1 already exists in the pinned 2.1.322 ("Code Mode (experimental)"); headless read-back 2026-11-16: no new tool, WebFetch dropped, ~3k fewer prompt tokens

A post the owner pasted on 2026-11-16 claimed that Code Mode arrives in Claude Code 2.1.323 behind
`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1`. It said the model writes a short script to search files,
using 2 turns instead of 13, and that this cuts tokens "from 150,000 to 2,000". That last figure is
Anthropic's MCP code-execution article, about MCP tool calls, not the terminal.

**Read-back on the pinned 2.1.322:**
- The binary already defines `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`, plus `_RESTART` and
  `_RESTARTED_FROM`, labelled "Code Mode (experimental)".
- Method: two headless `claude -p --output-format stream-json --verbose --max-turns 1` runs, one
  with the variable set and one without, comparing the init message's tools.
- With the variable set, the session had 73 tools against 74. `WebFetch` was gone and no new tool
  appeared. Cache creation was 12,709 tokens against 15,665, so the system prompt was about 3k
  tokens smaller.
- What the mode does inside a turn was not measured.

**How to apply:** this is not a fleet default. It is experimental, launch-time and undocumented,
and the fleet's "compute, then read" rule in AGENTS.md already asks for the script-first habit.
Adopting it is a routing/launcher env change. It needs a measured trial on one account, the same
task with and without the variable, comparing turns and tokens, with the result recorded under
docs/live-checks. Losing WebFetch matters to roles that read pages (moli remains). Related:
[[harness-pin-2-1-322-latest]].

*References: harness-pin-2-1-322-latest*

*Observed 2026-11-16 (fabric-coordinator)*

---
role: "rust-services-dev"
class: domain
topic: "claude-code-auto-compact-window-env"
description: "Forcing a Claude Code compaction cheaply: CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000 compacts at ~180k via the same reactive-compact agent (2.1.311)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - ed1b6ea2831c05a0
---

## Forcing a Claude Code compaction cheaply: CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000 compacts at ~180k via the same reactive-compact agent (2.1.311)

Measured on S32 probes (2026-11-10, Claude Code 2.1.311, claude-sonnet-5-5), and read from the binary.

- With `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000` the debug log shows `effectiveWindow=180000`, then `level=compact` and `routing through reactive (thresholdSource=env)`.
- The summary is written by the same `[reactive-compact]` forked agent that S31 saw at the host's own 980k window.
- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` also exists. Read from the binary: it lowers the threshold further, and a fork ignores it.
- Generated English prose costs about 0.33 tokens a byte. A 327,680-byte prose event is about 109k tokens, so two compact at a 200k window.
- A probe run cost 0.5 to 0.8M tokens, against 6.8M for S31 c at the full window.
- The transcript's `cost-state` entry carries `totalCostUSD`.

**Why:** forcing compaction at the host's window costs around 7M tokens a run.

**How to apply:** use the env var for compaction experiments, and state that it changes how many events share one summary. Related: [[claude-code-compacts-before-prompt-too-long]].

*References: claude-code-compacts-before-prompt-too-long*

*Observed 2026-11-10 (rust-services-dev)*

---
role: "rust-services-dev"
class: domain
topic: "claude-code-compacts-before-prompt-too-long"
description: "A channel event at the bridge bound in a long Claude Code conversation is not refused: the host auto-compacts first (2.1.311); DISABLE_COMPACT=1 to measure the refusal"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 0877b8c39c3a6b68
---

## A channel event at the bridge bound in a long Claude Code conversation is not refused: the host auto-compacts first (2.1.311); DISABLE_COMPACT=1 to measure the refusal

Measured in SPIKE-001 S30 (PR #580, 2026-11-06, Claude Code 2.1.311, facts 76-77):

- On claude-sonnet-5-5, claude-opus-5-5 and claude-haiku-5-5 each reports a 1,000,000-token `contextWindow`. One-letter filler costs about one token per byte, and so, roughly, does random base64url.
- A single event is refused ("Prompt is too long") at about 991,232 bytes or more.
- In a growing conversation the host never refuses. When the next prompt would pass `effectiveWindow=980000`, the debug log shows `autocompact ... level=blocked`, then `routing through reactive`. A forked `[reactive-compact]` agent runs for about 10 s, and the transcript gets a `system`/`compact_boundary` entry whose `compactMetadata` carries preTokens and postTokens.
- With 327,680-byte events, that happens every third event.
- `DISABLE_COMPACT=1` turns this off (the switch was read from the binary, not documented). With it set, the 4th event is refused.

**Why:** "Prompt is too long" in a multi-event conversation is the wrong thing to wait for. Compaction is the host's behaviour, and it silently replaces earlier events with a summary.

**How to apply:** record `result.usage`/`modelUsage`, the compact boundaries and the compaction summary's own text (S30 kept only the markers, and the raw was deleted after merge, so "what compaction keeps" needed a new run) in any context-size measurement. Set `DISABLE_COMPACT` only for a case that must reach the refusal, and say that the switch was read from the binary. Related: [[spike-facts-cite-committed-runs]].

*References: spike-facts-cite-committed-runs*

*Observed 2026-11-06 (rust-services-dev)*

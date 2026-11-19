---
role: "rust-services-dev"
class: domain
topic: "claude-code-host-line-cap-mode-flag-joining"
description: "Claude Code 2.1.311 channel host: 16 MiB stdout line cap, tokens per byte by content, what compaction keeps, when an event joins a turn, and the tengu_moss_anchor flag behind the unflagged -p mode"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 4a25b47c08a33276
---

## Claude Code 2.1.311 channel host: 16 MiB stdout line cap, tokens per byte by content, what compaction keeps, when an event joins a turn, and the tengu_moss_anchor flag behind the unflagged -p mode

Measured in InterWeave SPIKE-001 S31 (PR #606, 2026-11-09, facts 80-85), mostly on 2.1.311:

- **Line cap.** A stdio MCP server's stdout is buffered between message boundaries. Once a line plus its newline passes 16,777,216 bytes, the host logs `[ERROR] ... wrote >16MB to stdout without a JSON-RPC message boundary ... Disconnecting`, closes the transport and does not reconnect. A 16,777,215-byte line is delivered.
- **Tokens per byte, by content.** One letter repeated costs about 1.0 token a byte, the most of the nine kinds tried. Random printable ASCII costs 0.99, base64url 0.95, CJK 0.70, emoji 0.69, digits 0.33. U+0001 costs about 0, although the transcript holds those characters. A closing `</channel>` in a body becomes `<\/channel>`.
- **An event too large for the prompt.** It is either summarised by a `[reactive-compact]` agent (printable ASCII at 991,232 bytes) or refused "Prompt is too long" when that agent gets no usage (one letter at the same size).
- **What compaction keeps.** A summary keeps each event's number, a word in its head and the nonce. It keeps none of the body. The model then recalls those words correctly.
- **When an event joins a turn.** An event joins the running turn as a `queued_command` when that turn makes another model request (tool calls). It waits and starts a turn of its own when the turn only writes text. This holds for user-started and channel-started turns alike.
- **The unflagged `-p` mode.** In a non-interactive session the auto default needs the GrowthBook flag `tengu_moss_anchor`. Its built-in default is true on 2.1.286 and false on 2.1.311; the service serves false, and the value is cached in `.claude.json` `cachedGrowthBookFeatures`. To control it:
  - `DISABLE_GROWTHBOOK=1` makes the session use the built-in default;
  - setting the cached value true gives `auto`.
- **Random content can be refused by the API.** Three random base64url events (about 950k tokens) twice ended in the API error "safeguards flagged this message". Use one-letter content for long-context runs.

**Why:** these settle how a headless channel host must behave. Fact 75's "the mode follows the build" was really the flag's default.

**How to apply:** never count on the unflagged mode: pass `--permission-mode` or `--allowedTools`. Keep the turn making tool calls if events must join it. Re-measure the cap on any build other than 2.1.311. Related: [[claude-code-compacts-before-prompt-too-long]], [[claude-code-print-session-channel-facts]].

*References: claude-code-compacts-before-prompt-too-long, claude-code-print-session-channel-facts*

*Observed 2026-11-09 (rust-services-dev)*

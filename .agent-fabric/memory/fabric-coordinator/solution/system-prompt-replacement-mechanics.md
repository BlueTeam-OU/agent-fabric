---
role: "fabric-coordinator"
class: solution
topic: "system-prompt-replacement-mechanics"
description: "What --system-prompt-file replaces and what the harness still injects (read back live 2026-09-17), and the identifier rule a translated prompt must keep"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 92bebfae3d511438
  - 961300961ae6f116
  - c7c5469d544cd6a8
---

## What --system-prompt-file replaces and what the harness still injects (read back live 2026-09-17), and the identifier rule a translated prompt must keep

Read back live on Claude Code 2.1.274 and from its docs (2026-09-17), not re-probed since (the fleet runs
2.1.286 on 2026-10-23): `--system-prompt-file` replaces the harness's own instruction text and the
per-machine Memory section, and nothing else — the harness still sends, outside the file and in English, its
SDK opening line, the function-calling grammar, every tool schema, the agent/skill listings, MCP instructions,
CLAUDE.md (a user-turn reminder) and the reminders. There is no prepend and no settings key;
`--append-system-prompt-file` appends after the default. Tools are dispatched by `tool_use.name` against the
schemas, never by prose: a translated prompt is free in its prose and must keep every identifier it quotes
byte-identical (the harness text's own list is `fabric-locale tokens runtime/claude-code/harness/en.md`). The
harness text changes with the build and no flag prints it: its capture is a live-check duty
(`docs/live-checks/2026-09-17-claude-code-harness-prompt.md`).

**Why:** the owner wanted the ge holder launched with the whole prompt in Georgian, charter first; agent-fabric
ADR-027 ("The prompt in the locale") built the machinery on these facts.

Measured 2026-09-18 as the ge holder, one-turn calls, total input: the whole prompt replaced in Georgian
31 935 tokens; the old flow (English harness + the fabric's part appended) 38 438; the bare default 26 180.
`--disallowedTools` is variadic: pass it last or it eats a positional prompt.

**How to apply:** never translate identifiers; probe a harness claim from a fresh `claude -p` session before
designing on it, and re-capture the harness text on a new build; a lagging translation is served and named by
lint, never a failed launch. See [[subagent-tools-and-transcripts]].

*References: subagent-tools-and-transcripts*

*Anchors: `runtime/claude-code/harness/en.md`, `docs/live-checks/2026-09-17-claude-code-harness-prompt.md`*

*Observed 2026-10-23 (fabric-coordinator)*

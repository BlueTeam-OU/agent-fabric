---
role: "fabric-coordinator"
class: solution
topic: "system-prompt-replacement-mechanics"
description: "What --system-prompt-file replaces and what the harness still injects (read back on 2.1.274 and 2.1.311, from the request body), and the identifier rule a translated prompt must keep"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
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
  - 455057ff2ddd5792
  - 92bebfae3d511438
  - 961300961ae6f116
  - c7c5469d544cd6a8
---

## What --system-prompt-file replaces and what the harness still injects (read back on 2.1.274 and 2.1.311, from the request body), and the identifier rule a translated prompt must keep

Read back on Claude Code 2.1.274 from its docs and a live session (2026-09-17). Read again on 2.1.311
(2026-11-03, j560, docs/live-checks/2026-11-03-claude-code-2-1-311-readback.md R2), this time from the request
body itself, captured by a loopback listener with a dummy key. `--system-prompt-file` replaces the harness's own
instruction text and the per-machine Memory section, and nothing else. On 2.1.311 the request has three system
blocks: a billing header, the opening line `You are a Claude agent, built on Anthropic's Claude Agent SDK.`, and
the body, which becomes the file's text alone. Every tool schema, the agent listing, CLAUDE.md (in the first user
turn) and the reminders are still sent, in English, outside the file. There is no prepend and no settings key.
`--append-system-prompt-file` keeps the default body and appends after it; in that case the opening line reads
`You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK.` instead.
Tools are dispatched by `tool_use.name` against the schemas, never by prose: a translated prompt is free in its
prose and must keep every identifier it quotes byte-identical (`fabric-locale tokens
runtime/claude-code/harness/en.md`). The harness text changes with the build and no flag prints it. en.md is
still the 2.1.274 capture as of 2026-11-03: re-capturing it is a live-check duty, never a gate.

**Why:** the owner wanted the ge holder launched with the whole prompt in Georgian, charter first; agent-fabric
ADR-027 ("The prompt in the locale") built the machinery on these facts.

Measured 2026-09-18 as the ge holder, one-turn calls, total input: the whole prompt replaced in Georgian
31 935 tokens; the old flow (English harness + the fabric's part appended) 38 438; the bare default 26 180.
`--disallowedTools` is variadic: pass it last or it eats a positional prompt.

**How to apply:** never translate identifiers; read the request body (a loopback listener) rather than ask the
model; re-capture the harness text on a new build. Related: [[system-prompt-replacement-mechanics]].

*References: system-prompt-replacement-mechanics*

*Anchors: `tools/fabric/launch_prompt.py::--system-prompt-file`, `runtime/claude-code/harness/en.md::build:`*

*Observed 2026-11-03 (fabric-coordinator)*

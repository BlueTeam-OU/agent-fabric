---
role: "fabric-coordinator"
class: solution
topic: "subagent-tools-and-transcripts"
description: "What a Claude Code custom agent file's tools line really does (empty = every tool; none is refused), and what a subagent's transcript and sidecar carry — read back live 2026-09-17"
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
  - 50f2ddfab575626d
  - bf91c22085d998e5
---

## What a Claude Code custom agent file's tools line really does (empty = every tool; none is refused), and what a subagent's transcript and sidecar carry — read back live 2026-09-17

Probed on develop-qzapp with throwaway agent files, dispatched from a fresh headless session (an agent file is
read at session start; one written mid-session is "not found"): an empty `tools:` line or `tools: []` inherits
EVERY tool; a list that resolves to nothing (`tools: none`, an unrecognised name such as `TodoWrite`) makes the
harness refuse to spawn the agent at all; `disallowedTools` still leaves Monitor, SendMessage,
Enter/ExitWorktree and the MCP tools. A subagent with exactly one inert tool (`tools: TaskStop`, or
`ExitWorktree`) does spawn and can read and run nothing — that is the locale worker's shape
(`docs/live-checks/2026-09-17-language-culture-bridge.md`). Those tools-line facts were measured on 2.1.274
and not re-probed since.

A subagent's transcript is `<slug>/<session>/subagents/agent-<id>.jsonl` beside a sidecar
`agent-<id>.meta.json` whose `agentType` names the type dispatched; every transcript carries the hand-back as a
`tool_use` named `SubagentHandback` and injected `<system-reminder>` user records, so "no tool_use block"
identifies nothing and every user record is not the dispatcher's input (re-read on 2.1.286, 2026-10-23).

**Why:** the first cut of the language-culture worker said "no tools" and the `workers` measure keyed on
"no tool_use" — the blind review called both unproven, and the probes showed both wrong.

**How to apply:** design a fenced subagent as "one inert tool", identify subagent transcripts by the sidecar,
strip the reminder spans, and probe the harness from a fresh session before trusting a frontmatter field.
See [[blind-review-loop]].

*References: blind-review-loop*

*Anchors: `docs/live-checks/2026-09-17-language-culture-bridge.md`*

*Observed 2026-10-23 (fabric-coordinator)*

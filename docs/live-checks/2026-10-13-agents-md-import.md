# 2026-10-13 — Claude Code reads AGENTS.md through CLAUDE.md's import

Run by fabric-coordinator, as the login user, on Claude Code 2.1.286, in a worktree of the branch `develop-qzapp/user/adr-054/agents-md` at 82376301 (the split of ADR-054 piece 1): `CLAUDE.md` is `# … in Claude Code`, `@AGENTS.md`, then the Claude Code section; `AGENTS.md` is the former `CLAUDE.md` less that section.

## What was measured

`claude -p --output-format stream-json --verbose` with every tool disallowed, the prompt on stdin, asked to answer from its loaded instructions only. The first assistant message (the Stop hook's later turn ignored):

| asked | answered | from |
|---|---|---|
| the first line of the code block under "The invariant" | `Linux login identifies the agent.` | `AGENTS.md` |
| the first words of the `**Subagents**` bullet | "Subagents name a capability class in `subagent_type` — the" | `CLAUDE.md`'s own section |
| the sentence starting "This file holds what is true" | quoted whole | `AGENTS.md`, new in this branch |
| the instruction files given, by path | `/tmp/wt-agents/CLAUDE.md` ("imports AGENTS.md and adds the Claude Code section") and `/tmp/wt-agents/AGENTS.md` | — |

## What it decides

ADR-054 §5 rule 1 holds for Claude Code: a session launched in the repository reads `AGENTS.md` whole through `CLAUDE.md`'s `@AGENTS.md`, and the Claude-only section beside it, so the split changes nothing a Claude session reads. Codex's own discovery of `AGENTS.md` is §8 piece 2's check, not this one.

## Not verified

- A session started in `projects/` (the workspace `CLAUDE.md` imports `agent-fabric/CLAUDE.md`, which imports `AGENTS.md`: a two-level import, the same mechanism, not run).
- A subagent's context (the review class reads the same files as a harness property, not run here).

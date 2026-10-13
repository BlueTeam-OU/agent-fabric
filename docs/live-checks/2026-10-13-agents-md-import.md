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

## The two-level import, from a project's working copy

A fleet session starts in a project's working copy, where Claude Code loads the workspace `projects/CLAUDE.md`, which imports `agent-fabric/CLAUDE.md`, which now imports `AGENTS.md`. Rebuilt in the scratchpad: a `projects/` with the workspace template (`runtime/claude-code/workspace/CLAUDE.md`), `agent-fabric` a link to the checkout under test, and an empty git repository `someproj` to start in, the same prompt.

- Without the external-include approval for `someproj` (`hasClaudeMdExternalIncludesApproved` in `~/.claude.json`), neither the split nor the control loaded `agent-fabric/CLAUDE.md`: an import outside the git root is not read unapproved. The approval was then set for that one scratch path and removed after the runs.
- **Control**, `agent-fabric` → main (unsplit): the invariant line quoted; the new sentence absent; the files received: `projects/CLAUDE.md`, `agent-fabric/CLAUDE.md`.
- **Split**, `agent-fabric` → the branch: the invariant line quoted; the new sentence quoted; the `**Subagents**` bullet quoted; the files received: `projects/CLAUDE.md`, `agent-fabric/CLAUDE.md`, `AGENTS.md` (resolved beside `agent-fabric/CLAUDE.md`, through the link).

A working copy whose external includes are not approved loads none of the fabric's rules, split or not: on 2026-10-13 `~/.claude.json` of the login user had them off for `dcs`, `gzapp.decks` and three `gzapp-claude*` copies (job j62).

## What it decides

ADR-054 §5 rule 1 holds for Claude Code: a session launched in the repository reads `AGENTS.md` whole through `CLAUDE.md`'s `@AGENTS.md`, and the Claude-only section beside it, so the split changes nothing a Claude session reads. Codex's own discovery of `AGENTS.md` is §8 piece 2's check, not this one.

## Not verified

- A subagent's context (the review class reads the same files as a harness property, not run here).

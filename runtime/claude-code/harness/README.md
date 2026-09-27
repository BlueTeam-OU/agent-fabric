# The harness's own system prompt, as a source for translation

`en.md` is the text Claude Code puts before the fabric's appended prompt
— Anthropic's, not ours — captured verbatim from a live session
(`docs/live-checks/2026-09-17-claude-code-harness-prompt.md`), with the
one login-specific span, the memory directory, replaced by the
placeholder `{memory_dir}` that `tools/fabric/launch_prompt.py` fills at
render (`harvest_memory.default_memory_dir`, the path the harness uses).

It exists so a locale can translate it: a language-culture login whose
locale carries `locale/<suffix>/harness.md` is launched with
`--system-prompt-file` — the fabric's prompt, in the locale, then this
text in the locale — in place of the harness's English
(`docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md` §5 rule 9). What a
replacement does NOT touch, because the harness sends it outside the
replaceable text: the function-calling grammar, every tool schema, the
agent and skill listings, the MCP instructions, CLAUDE.md, the
reminders. What it drops is this text and the per-machine Memory
section — which is why the Memory section is in here with its path as a
placeholder.

**As captured, verbatim.** The text carries the harness's own slips
(build 2.1.274: "it's clickable.Write code that reads…" — two sentences
glued at a lost newline), and they stay: the file is what the harness
sends. The token list therefore counts that `Write` as a tool name, and
a translation keeps a literal `Write` there (the ge holder, 2026-09-17).

**Refreshing it.** No flag prints the default prompt; the text changes
with the CLI build. The capture is a live-check duty: from a session on
a new build, record the text as the live check did, update `en.md` and
its `build`, and every translation lags by digest until its holder
re-renders it — served meanwhile (a launch never fails on lag), named
by `tools/fabric/lint.py`. The launcher stamps the build it ran
(`AGENT_FABRIC_LAUNCH_CLAUDE_VERSION`) beside `build:` here, so a build
that moved past the capture is visible, never a gate.

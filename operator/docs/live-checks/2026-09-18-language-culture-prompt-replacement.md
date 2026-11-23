# The whole prompt in the locale, read back — 2026-09-18

The plan of 2026-09-17 (`docs/language-culture-bridge.md`, "The prompt
in the locale") landed as `8bc5cf6`…`87dd3e1` (sources, lint, the
renderer, the launcher, the carve-out) and the holder's translation as
PR #3, merged at `3bdf099`. Measured on `develop-qzapp` as
`language-culture-ge`, through the host executor, on Claude Code
2.1.275.

## The launch

- `runtime/openrouter/launch --provider anthropic --print`:
  `launch-prompt.md (71 712 bytes; --system-prompt-file)` and
  `AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=2.1.275` — the flag flipped by
  the presence of `locale/ge/harness.md`, and the stamp already one
  build past the capture (`runtime/claude-code/harness/en.md` says
  2.1.274): a re-capture is due, the next live-check duty, and
  nothing fails meanwhile.
- `launch_prompt.py --print`: `replace: yes`; the headings in order —
  `# ვინ ხარ`, `# language-culture — ქარტია`, `# language-culture —
  ბრიფი`, `# გუნდთან მუშაობა`, `# შენი გრძელვადიანი მეხსიერება`, then
  the harness sections `# გარსი`, `# სესიის სპეციფიკური მითითებები`,
  `# მეხსიერება`, `# გარემო`, `# კონტექსტის მართვა`, `# სამუშაოს
  მიწოდება`, `# შესწორებები`. No English heading remains (the
  missing-brief heading was the last, folded into its template at
  `87dd3e1`). No placeholder remains; the memory section names
  `/home/language-culture-ge/.claude/projects/-home-language-culture-ge-projects-agent-fabric/memory`
  — `layout.default_memory_dir` of the launch cwd, the directory the
  harness itself keeps.
- **The kill switch, tried:** `locale/ge/harness.md` moved away →
  `launch --print` says `(44 574 bytes; --append-system-prompt-file)`
  and `replace: no`; moved back, the tree is clean. (Note for the next
  reader: `--print` renders the state file as a side effect; render
  again after such a probe.)

## The session under the replaced prompt

A headless call as the holder, `claude -p … --system-prompt-file
<the rendered file> --disallowedTools WebSearch`, on haiku:

- It ran `id -un` with the Bash tool and answered `language-culture-ge`;
  it reported no tool named `WebSearch`, and its MCP tools as
  `mcp__websearch-locale__web_search`,
  `mcp__websearch-locale__web_search_global` and the Claude Docs
  tools; it said its system prompt is written in Georgian, "as
  evidenced by the charter that begins this session". The mechanics
  the replacement does not touch — the function-calling grammar, the
  tool schemas, the MCP tools — all in place.
- `--disallowedTools` is variadic and ate the positional prompt when
  it preceded it: the launcher now passes it last, after the caller's
  arguments (`runtime/openrouter/launch`, its test).

## The cost, measured

One-turn calls ("Reply with the single word OK"), total input
(`input_tokens` + cache creation + cache read), same account, same cwd:

| prompt | total input tokens |
|---|---|
| the default English prompt, nothing appended | 26 180 |
| the old flow: English harness + the fabric's part appended (Georgian charter, English shared sections; 44 574 bytes) | 38 438 |
| **the new flow: the whole prompt replaced, in Georgian (71 712 bytes)** | **31 935** |

The whole prompt in the locale costs *less* than the old flow — the
English harness text is gone, and the harness's own additions (tool
schemas, listings, CLAUDE.md) dominate both. The per-body estimates
of 2026-09-17 (2.9× tokens for Georgian) were differenced across
cached prefixes and overstated the total; these three are the numbers
to keep.

## The holder's review, and the fence

The blind review of the holder's range found one P2 — the source's
glued "clickable.Write code…" rendered as "write the code *with
`Write`*", an instruction the source does not carry: the token rule
keeps the identifier, the review caught the meaning — and the holder
closed it in its fix commit (`8131f4f`), with the term consistency and
the wraps; two cosmetic wraps remain for a follow-up. The fence had to
move for the PR to exist at all (`5e52920`, `ae72b8e`: the locale
carve-out, and a merge of `main` into a locale branch judged by what
the branch adds), and the two test fixtures that failed on the
holder's own login were the tests' assumptions (`6e46aa1`). After
this, no Georgian text in the fabric has any author but its holder.

Not yet read back: an interactive relaunch of the holder — the worker
dispatched under the replaced prompt, a skill invoked, the `script`
op's `workers` and notes language after it — asked of the holder.

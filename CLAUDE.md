@AGENTS.md

## Claude Code

What follows holds only in a Claude Code session; everything above is
the same in any harness (ADR-054).

- **Memory.** Durable new knowledge goes to your own Claude memory, one
  fact per file, with a `roles_class` in its `metadata:` block; only a
  file that opts in is drained.
- **Subagents** name a capability class in `subagent_type` — the five
  are `code-low`, `code-medium`, `code-high`, `code-plan` and the review
  class `code-review` — and in `model` the harness tier alias that class
  rides (`runtime/claude-code/aliases.json`: `haiku`, `sonnet`, `opus`,
  `fable`; `fable` for `code-plan` and for a review), never a vendor
  model. What a class resolves to is `routing/`, decided at launch. The
  dispatch guard refuses a class dispatch whose `model` is not its alias
  (unset included), a review on anything but `fable`, and a writing
  dispatch without worktree isolation; `code-high` and `code-plan` ask.
  The read-only harness types (`Explore`, `Plan`, `claude-code-guide`)
  name a model and no isolation. `locale-worker` exists on the
  language-culture logins only.
- **How much a class thinks is routed too** (`routing/effort.json`),
  written into each class's agent file at launch. Never set it per
  dispatch, and never through `CLAUDE_CODE_EFFORT_LEVEL`, which the
  launcher refuses (ADR-006).

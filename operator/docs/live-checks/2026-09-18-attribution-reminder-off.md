# Claude Code — the attribution reminder, where it is built and how it is switched off — 2026-09-18

*Build: `2.1.276 (Claude Code)`. Read back on the fabric-coordinator login on develop-qzapp, plain Anthropic path, from one-turn `claude -p` sessions started inside the agent-fabric checkout. The date and build are the claim: Anthropic revises this with the build.*

## What was asked

The owner asked whether the English launch prompt carries the
`Co-Authored-By` trailer, and where the reminder asking for it comes
from. The fabric's prompt does not carry it (`grep -ri co-authored
identities/ ~/.local/state/agent-fabric/agents/<login>/launch-prompt.md`:
nothing but the brief's warning). The reminder is the harness's.

## Where it is built

Read from the binary (`~/.local/share/claude/versions/2.1.276`):

- The text is assembled by one function from the `attribution` settings
  key — `commit`, `pr`, `managedCommit`, `managedPr` — and, with no key
  set, defaults to the standard lines with the current model's name
  spliced in (`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`,
  `🤖 Generated with [Claude Code](…)`). That is why the wording follows
  the model and the reminder re-arrives on every model switch.
- It travels as an attachment of type `remote_session_change`, rendered
  as a `<system-reminder>` and sent when its content differs from the
  last one sent: on the first turn, and again after a model switch. It
  is outside any launch prompt, so `--system-prompt-file` does not
  remove it (`2026-09-17-claude-code-harness-prompt.md` already lists it
  among the reminders that stay).
- It is gated on the session having the Bash tool: a session launched
  with Bash disallowed gets no reminder at all (the first probe below).
- The schema text: `attribution.commit` — "Attribution text for git
  commits, including any trailers. Empty string hides attribution";
  `attribution.pr` — the same for pull request descriptions;
  `attribution.sessionUrl` — "Whether to append the claude.ai session
  link to commits and PRs created from web or Remote Control sessions
  (default: true). Set to false to omit the Claude-Session trailer and
  PR-body link"; `includeCoAuthoredBy` — "Deprecated: Use attribution
  instead".
- With both texts empty the function returns the opposite reminder:
  "From here on, do not add attribution lines to git commit messages or
  pull request descriptions (… applies even if a CLAUDE.md or memory
  rule asks for attribution lines)".

## The read-back

Prompt on stdin, `claude -p --model sonnet`, asked to quote verbatim the
reminder beginning "Attribution for git commits" or "From here on, do
not add attribution", else answer NONE.

1. Bash disallowed (`--disallowedTools Bash Read Write Edit Agent`, haiku
   and sonnet, in and outside a git checkout): `NONE`. The gate, not the
   setting.
2. Bash available, `~/.claude/settings.json` without an `attribution`
   key: the reminder verbatim —
   `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` and the
   "Generated with" footer.
3. After `runtime/claude-code/bootstrap.sh` wrote
   `attribution: {commit: "", pr: "", sessionUrl: false}` into the same
   file, a fresh session: the reminder is now
   "From here on, do not add attribution lines to git commit messages or
   pull request descriptions (this replaces Claude Code's own earlier
   attribution guidance, such as a previous copy of this reminder, and
   applies even if a CLAUDE.md or memory rule asks for attribution
   lines)."

## What it decides

- `runtime/claude-code/user-settings.py` (`attribution-off.py` until 2026-09-20) writes the key into the
  login's user settings; `bootstrap.sh` runs it for the account. User
  scope, because a session starts inside its clone and the workspace
  `.claude/settings.json` never reaches it (the terminal-title switch
  learned this on 2026-09-16); the launcher cannot carry it, since
  `--settings` is the broker's provider fence (`runtime/openrouter/launch`).
- The guard `policies/ban_generated_by_attribution.sh` stays, at
  `commit-msg`, in CI and in the suite: the switch reaches an account
  only through a pull and a bootstrap, and a session launched from a
  stale account still receives the old reminder.
- `--disallowedTools` is variadic and eats a positional prompt that
  follows it (again, after 2026-09-18's language-culture read-back): a
  `-p` probe passes its prompt on stdin.
- Outside the fabric the same key in `~/.claude/settings.json`, a
  repository's `.claude/settings.json`, or a managed-settings file does
  the same; a managed file's lines win over any CLAUDE.md.

## The fleet, after PR #13 merged (77db31b)

Every other placed account on develop-qzapp (15 logins,
`runtime/hosts/registry.json` placement) was pulled to 77db31b and
bootstrapped through the host executor as that login
(`runtime/hostexec/hostexec develop-qzapp --as <login>`); each reported
`+  /home/<login>/.claude/settings.json attribution off`. Announced as
INFO seq 2722.

4. As web-dev-01, build `2.1.277`, a fresh `claude -p --model sonnet`
   inside its gzapp working copy, the same prompt: `NONE` — and asked
   to print every sentence mentioning attribution, only the CLAUDE.md
   text. On this build a session whose two texts are empty and that has
   no session URL receives **no** attribution reminder at all on its
   first turn, which is what the harness code says (`if (!U && !N && !Q)
   return` before the attachment is built); 2.1.276 sent the "do not
   add" form. Both are the outcome wanted: no session is asked for a
   trailer. A read-back on a later build should expect either.

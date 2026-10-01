---
role: "fabric-coordinator"
class: solution
topic: "claude-setup-token-facts"
description: "What a `claude setup-token` token can and cannot do, how to tell which account it belongs to, and that CLAUDE_CODE_OAUTH_TOKEN beats a stored sign-in — measured 2026-09-24 on 2.1.281"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
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
  - 056b762f847c9da3
---

## What a `claude setup-token` token can and cannot do, how to tell which account it belongs to, and that CLAUDE_CODE_OAUTH_TOKEN beats a stored sign-in — measured 2026-09-24 on 2.1.281

Measured 2026-09-24, Claude Code 2.1.281, for the two-account templates in Doppler
(project agent-fabric, environment `claude-accounts`, one config per Claude account,
key `CLAUDE_CODE_OAUTH_TOKEN`).

- The token is `sk-ant-oat…`, 108 chars, inference-only: `api/oauth/profile` and
  `api/oauth/usage` answer **403**. The control daemon's `identity`/`usage` ops
  (runtime/control/ops.mjs, which read `.credentials.json`) cannot use it.
- Which account a token belongs to: a 1-token `/v1/messages` call with
  `anthropic-beta: oauth-2025-04-20` returns `anthropic-organization-id`; compare it
  with `~/.claude.json` `.oauthAccount.organizationUuid` of a login known to be on
  that account. The first attempt stored two tokens of the SAME account — the token
  belongs to whichever account the BROWSER approves in, not the CLI's login.
- `CLAUDE_CODE_OAUTH_TOKEN` in the environment wins over `.credentials.json`: with
  an invalid stored sign-in, no token → "OAuth session expired and could not be
  refreshed"; with either template's token → served.
- `claude -p --output-format json` prints a JSON ARRAY of events on 2.1.281; read
  `.[] | select(.type=="result")`.
- `pkill -f "claude setup-token"` from a Bash tool matches the tool's own shell and
  kills it (exit 144) — match on the process name, not the full command line.
- A `!` command has no TTY and a 120 s limit: `claude setup-token` there never
  returns a token; it must run in the person's own terminal.

- One template token served web-dev-01 (no own sign-in at all) and db-admin
  concurrently, both `claude -p` ok.
- A `/login` sign-in has six scopes and an 8-hour access token plus a refresh
  token; a setup-token has `user:inference` only (claude.ai Settings → Claude Code
  lists both kinds). No token is both shared and full-scope.
- `claude auth status` does NOT renew an expired sign-in: it reports the cached
  email/orgId/plan, starts a refresh, exits, and leaves `~/.claude/.oauth_refresh.lock`
  (a DIRECTORY — `rmdir`, not `rm`); a run within the next 60 s fails "another
  Claude Code process is refreshing it" — the harness's lockfile is `stale:
  60000` under the config dir (`Kd(claudeDir, ".oauth_refresh.lock")`), so it
  clears itself after a minute. A one-word `claude -p` renews it; after that
  `fabric-ctl <login> usage` reads the windows again. The fleet's "read-failed"
  usage is expired sign-ins on logins with no session running.

- **`claude -p "/usage" --output-format json` is the usage observer**: no model
  call (0 turns, $0), it RENEWS an expired sign-in (backend-dev-02: expired 15:31Z,
  run 18:32Z, valid to 02:32Z after) and leaves no lock; the assistant event carries
  `usage_report.rate_limits.limits[]` = {kind session|weekly_all|weekly_scoped,
  group, percent, resets_at, scope}. `weekly_scoped` (per-model) is not in
  `api/oauth/usage`'s answer. Preferred over reimplementing the refresh (Claude
  Code's client_id at platform.claude.com/v1/oauth/token): official client, no ToS
  question.

Not established: Doppler cross-config reference syntax for pointing a login
config at a template. See
[[redirecting-a-request-moves-its-credential]].

*References: redirecting-a-request-moves-its-credential*

*Observed 2026-09-24 (fabric-coordinator)*

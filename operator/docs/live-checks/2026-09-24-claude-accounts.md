# 2026-09-24 — two Claude accounts, one fleet: what was measured

Claude Code 2.1.281 on develop-qzapp. The owner asked to move logins
between two Claude subscriptions without a browser login per login, and
to read each account's usage. Every check printed hashes, organisation
ids and HTTP codes — never a token.

## A setup-token is inference-only

Both templates' tokens: `sk-ant-oat…`, 108 characters. `GET
api/oauth/profile` and `api/oauth/usage` with them: **403**. claude.ai →
Settings → Claude Code lists a setup-token with the single scope
`user:inference`, beside the `/login` sign-ins with six.

## Which account a token belongs to

A one-token `POST /v1/messages` (`anthropic-beta: oauth-2025-04-20`) returns
`anthropic-organization-id`. The first attempt stored two DIFFERENT tokens
(distinct sha256) whose requests both answered organisation `835529e5…` —
the browser had been signed into the same account both times. After the
pzhuy template was redone in a browser signed in as that account, it
answered `c8db462b…`, the organisation this coordinator's own `/login`
records. Both tokens of the first attempt answered 200 at the same moment:
an account holds several valid setup-tokens.

## The token outranks a stored sign-in

A scratch `CLAUDE_CONFIG_DIR` holding a deliberately invalid
`.credentials.json`, `claude -p` with a one-word prompt:

```
no token                    is_error: true  "Failed to authenticate: OAuth session expired and could not be refreshed"
+ either template's token   is_error: false "ok"
```

## One token, many logins, at once

The pzhuy template's token handed over stdin (hostexec) to web-dev-01 and
db-admin concurrently: both requests `c8db462b…`, both `claude -p` "ok".
web-dev-01 had no sign-in of its own at all (no `.credentials.json`, no
`oauthAccount`), so the token alone suffices.

## A login resolves a reference into a template

`CLAUDE_CODE_OAUTH_TOKEN=${agent-fabric.claude-accounts_claude-pzhuy-8alias-com.CLAUDE_CODE_OAUTH_TOKEN}`
set in `agents2_web-dev-01`; read back AS web-dev-01 with its own read-only
service token: resolved, sha256 `26f5543797ba` — the template's own. (A
`doppler --plain` value ends in a newline; a fingerprint hashes it without.)

## /usage is the observer

`claude -p "/usage" --output-format json` (the output is a JSON array of
events on 2.1.281): 0 turns, `total_cost_usd` 0, no model used; the
assistant event carries `usage_report.rate_limits.limits[]` — `session` 11%,
`weekly_all` 83%, `weekly_scoped` 86%, each with `resets_at`. The last is
not in `api/oauth/usage`'s answer.

On backend-dev-02, whose sign-in had expired at 15:31Z and had no session
running: the same command at 18:32Z returned the windows and left the
sign-in valid to 02:32Z the next day, no lock behind.

## `claude auth status` is not a keep-alive

On db-admin (sign-in expired 07:51Z, no session): `auth status --json`
reported the cached email, organisation and plan, did not move the expiry,
and left `~/.claude/.oauth_refresh.lock` — a directory. The next
`claude -p` failed "another Claude Code process is refreshing it or exited
mid-refresh". `rmdir` of the lock (the owner, by hand), then `claude -p`:
"ok", expiry moved to 01:51Z, and `fabric-ctl db-admin usage` read the
windows again. The run that failed came within a minute of `auth status`:
the harness takes its refresh lock as a lock directory named
`.oauth_refresh.lock` in the config directory it runs with, and declares
it stale after 60 s (`stale: 60000`, read from the 2.1.281 and 2.1.282
binaries after this check), so a lock left this way blocks for a
minute, not for good. The fleet's `read-failed` usage rows that morning were
expired sign-ins on logins with no session to renew them.

## What this decides

Templates for the working sessions, a harness-driven observer for the
windows (`docs/claude-accounts.md`). Not established: a limit on
setup-tokens per account (none documented), and how the observer behaves
across a Claude Code update mid-read.

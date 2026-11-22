# 2026-10-24 — what a Claude account tells the fabric about itself

Run by fabric-coordinator, as the login user, on Claude Code 2.1.286 (job j373). The owner asked for each account's reset hours in the account metadata kept in the coordinator's store (`settings/accounts/<slug>.json`), and for as much of that metadata as the fabric can read without a person. The question: what each of the fabric's two credentials for an account answers, and what only the account's billing page holds.

The two credentials: the one-year setup-token each account's template holds (`CLAUDE_ACCOUNT_<SLUG>` in the coordinator's store; every working session runs on one), and an observer sign-in, a Claude Code config directory signed in with `/login` under `<state>/accounts/<slug>/` (ADR-031). On this day all three accounts have a template; one has an observer sign-in.

## What was measured

**The setup-token, all three accounts.** One `POST /v1/messages` per token (the pinned Haiku id, `max_tokens` 1, as `ops/usage.py` probes), the token in one header and printed nowhere. Each reply carried, besides its request id:

| header | values seen |
|---|---|
| `anthropic-ratelimit-unified-5h-utilization`, `-5h-reset`, `-5h-status` | 0.0–0.26; epoch seconds; `allowed` |
| `anthropic-ratelimit-unified-7d-utilization`, `-7d-reset`, `-7d-status` | 0.0, 0.76, 1.0; epoch seconds; `allowed`, `allowed_warning`, `rejected` |
| `anthropic-ratelimit-unified-7d-surpassed-threshold` | 0.75, 1.0 (absent below the first threshold) |
| `anthropic-ratelimit-unified-status`, `-reset`, `-representative-claim` | the binding window: `seven_day` or `five_hour` |
| `anthropic-ratelimit-unified-overage-status`, `-overage-disabled-reason` | `rejected`; `out_of_credits` (two accounts), `org_level_disabled` (one) |
| `anthropic-ratelimit-unified-fallback-percentage`, `-upgrade-paths` | 0.5; `overage` (absent on one) |
| `anthropic-organization-id`, `anthropic-workspace-id` | one of each per account, distinct across the three |

The account whose weekly limit was spent answered HTTP 429 with the same headers, so a probe reads an exhausted account too. The weekly resets read back (Thursday 12:00, Monday 16:00, Thursday 18:00 UTC) were the ones the owner read off each account's usage page the same day. The probe opened a five-hour window on the two idle accounts (their `5h-reset` moved to five hours after the probe, 0% used). A token reads nothing else: `GET /api/oauth/usage`, `/api/oauth/profile`, `/api/oauth/account` and `/api/oauth/claude_cli/roles` each answered 403.

**The observer sign-in, one account.** Its `.claude.json` `oauthAccount` holds `organizationType` (`claude_max`), `organizationRateLimitTier` (`default_claude_max_20x`), `billingType` (`stripe_subscription`), `subscriptionCreatedAt`, `hasExtraUsageEnabled`, `organizationName`, `organizationRole`, `accountCreatedAt` and the display names. Its `subscriptionCreatedAt` falls on the 17th, and the billing page gives the renewal as the 17th of next month.

`claude -p /usage --output-format json --no-session-persistence`, the command `read_account` runs, now prints only the final `result` object: its `result` is the report as text, and there is no `usage_report`. `parse_usage_report` reads that as `unreadable`, which is what `fabric-accounts read` printed. With `--verbose` added, the output is again an array of events (3 here), one of them carrying `usage_report.rate_limits.limits`: `session`, `weekly_all` and `weekly_scoped`, the last scoped to a model (`Fable`), each with `percent` and `resets_at`. `--output-format stream-json --verbose` gives the same events one per line. Without stdin redirected the harness waits 3 s for it and says so on stderr.

## What it decides

- **Read by the fabric, for every account with a template, no person needed:** both windows' utilization, reset time and status; the weekly reset's weekday and hour; whether extra usage is possible and why not; the organization and workspace ids. That is what `usage_resets` in the store's account files needs, so it is written by the fabric, not typed from a page.
- **Read only through a sign-in:** the plan's type and tier, the billing type, the subscription's start (and so the renewal's day of the month, a derivation checked once, not a field), the extra-usage switch, and the per-model weekly meter.
- **Only on the billing page:** the renewal date as such, the payment card, and the API-credit organization, amount and next credit date. These stay the owner's to give.
- **The observer read is broken on 2.1.286** and needs `--verbose` (and stdin from `/dev/null`). Until it lands, a sign-in's per-model meter is not read.

## Not verified

- When the json output lost its event array (the 2026-09-24 check, on 2.1.281, saw it without `--verbose`).
- Whether the per-model meter exists for an account without a sign-in by any other route.
- Whether a probe of an idle account costs anything beyond opening its five-hour window.
- The renewal-day derivation on the two accounts without a sign-in.

# 2026-10-08 — A setup-token's usage windows, read from an inference reply

The owner asked for the weekly allowance of the two Claude accounts. `fabric-ctl all usage` printed `setup-token` for every login and no figure: every account runs on a one-year setup-token, which is `user:inference` only, and the usage endpoint (`/api/oauth/usage`) answers it 403 (ADR-031). The question was whether the windows reach a setup-token any other way.

## The probe

One `POST /v1/messages` per account, on develop-qzapp as user:
- the account's own setup-token, as `Authorization: Bearer`, with `anthropic-beta: oauth-2025-04-20`;
- model `claude-haiku-4-5-20251001`, `max_tokens` 1, a one-character prompt.

The token was read from the store by the script and went into that one header; nothing printed it.

## What came back

HTTP 200 for both templates, each with the full `anthropic-ratelimit-unified-*` set:

| header | template A | template B |
|---|---|---|
| `5h-utilization` | 0.09 | 0.01 |
| `5h-status` | allowed | allowed |
| `7d-utilization` | 0.78 | 0.24 |
| `7d-status` | allowed_warning | allowed |
| `7d-surpassed-threshold` | 0.75 | — |
| `overage-status` | rejected | rejected |

Also present: `5h-reset` and `7d-reset` (epoch seconds), `status`, `representative-claim` (`seven_day`), `fallback-percentage`, `overage-disabled-reason` (`out_of_credits`).

The control: the two accounts answered with different figures and different 7-day resets (Thu 12:00 and Mon 16:00 UTC). The headers are each account's own, not a constant.

## What it decides

- **The control agent's `usage` op reads a setup-token account from these headers** (`runtime/control/ops/usage.mjs`).
  - One one-token call, against the account's own allowance.
  - The utilisation is reported as the usage endpoint reports it, a percentage, with the reset as an ISO time and the window's status beside it.
  - A 429 still carries the headers, so a full window is a reading, not a failure.
- **The probe model is a pinned id, not routing's.** The probe must not change with what a class rides.
- **Not measured:** whether the headers come back on a model other than Haiku 4.5, and whether they count a one-token call differently from a session's.

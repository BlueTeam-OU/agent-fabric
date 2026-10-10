---
role: "fabric-coordinator"
class: solution
topic: "claude-setup-token-facts"
description: "A claude setup-token token is inference-only; account templates live in the coordinator's store, usage of such accounts comes from rate-limit headers"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
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
  - ce18a1be0e33ec93
---

## A claude setup-token token is inference-only; account templates live in the coordinator's store, usage of such accounts comes from rate-limit headers

Measured 2026-09-24 on Claude Code 2.1.281; re-check the facts below on a newer build.

- The account templates are entries `CLAUDE_ACCOUNT_<SLUG>` in the coordinator's own pass store (ADR-031, ADR-038; Doppler is retired). `fabric-accounts assign` gives one to a login as `CLAUDE_CODE_OAUTH_TOKEN`.
- The token is `sk-ant-oat...`, inference-only (`user:inference`). `api/oauth/profile` and `api/oauth/usage` still answer 403 to it, so the control agent's `usage` op reads such an account's windows from the `anthropic-ratelimit-unified-*` headers of a one-token `/v1/messages` reply (tools/fabric/control/ops/usage.py, runtime/control/ops/usage.mjs; docs/live-checks/2026-10-08-usage-from-inference-headers.md).
- Which account a token belongs to: a one-token `/v1/messages` call with `anthropic-beta: oauth-2025-04-20` returns `anthropic-organization-id`; compare it with `~/.claude.json` `.oauthAccount.organizationUuid` of a login on that account. The token belongs to the account the BROWSER approved, not the CLI's login.
- `CLAUDE_CODE_OAUTH_TOKEN` in the environment wins over `.credentials.json`.
- `claude -p --output-format json` prints an ARRAY of events; read `.[] | select(.type=="result")`.
- `pkill -f "claude setup-token"` from a Bash tool kills the tool's own shell; match the process name.
- `claude setup-token` needs a TTY and more than 120 s: it runs in the person's own terminal.
- `claude auth status` does not renew an expired sign-in and leaves `~/.claude/.oauth_refresh.lock` (a directory, stale after 60 s). `claude -p "/usage" --output-format json` makes no model call, renews an expired sign-in, and its assistant event carries `usage_report.rate_limits.limits[]` (session, weekly_all, weekly_scoped).

*Observed 2026-10-10 (fabric-coordinator)*

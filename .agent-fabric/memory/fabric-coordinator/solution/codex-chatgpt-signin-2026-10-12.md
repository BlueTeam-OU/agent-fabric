---
role: "fabric-coordinator"
class: solution
topic: "codex-chatgpt-signin-2026-10-12"
description: "Codex signed in to ChatGPT (team plan) in ~/.codex-chatgpt on develop-qzapp; device codes are off in the workspace, plain `codex login` worked; auth.json shape and what a real exec showed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 87917e79535ef708
---

## Codex signed in to ChatGPT (team plan) in ~/.codex-chatgpt on develop-qzapp; device codes are off in the workspace, plain `codex login` worked; auth.json shape and what a real exec showed

2026-10-12: Codex CLI 0.162.1 installed on my login (fabric-tools --install codex, after #222 raised the
installer's size bound to 512 MiB: tarball 158 MiB, binary 281 MiB). The owner signed in with plain
`codex login` (browser on the same machine, redirect to localhost) because the ChatGPT workspace has
**device codes disabled** (`--device-auth` refused: "contact your workspace admin"). Sign-in lives in
`CODEX_HOME=~/.codex-chatgpt` (0700), never `~/.codex` (ADR-053 rule 3).

`auth.json` (0600): `auth_mode` "chatgpt", `OPENAI_API_KEY` null, `tokens.{id_token, access_token,
refresh_token, account_id}`, `last_refresh`. The access token is a JWT with a **240 h lifetime**; the id
token 1 h; the refresh token is opaque (196 chars). Plan claim: `team`. `account_id` equals the access
token's `chatgpt_account_id`.

A real `codex exec --sandbox read-only --skip-git-repo-check --cd D --output-schema S
--output-last-message F --color never -` with `fabric-review`'s answer schema answered
`{"findings": []}` (14.5k tokens for a one-line prompt): every flag the engine passes exists and the
strict structured-output schema is accepted. Not yet confirmed: refresh behaviour, and the header that
carries the access token through a gateway (ChatGPT-Account-ID beside Authorization per the spike).

**Why:** the review engine's launcher profile (ADR-053 §6) needs this credential held by the gateway.
**How to apply:** build the profile from this shape; never print or copy the tokens. Related:
[[codex-decisions]], [[api-key-credit-coordinator-only]].

*References: api-key-credit-coordinator-only, codex-decisions*

*Observed 2026-10-12 (fabric-coordinator)*

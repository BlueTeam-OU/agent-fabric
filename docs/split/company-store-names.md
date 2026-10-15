# Company stores — the names to move (for the owner's review)

Which entries leave the agents' own stores for a company's store (ADR-038 rule 10), and
which stay. Proposed by fabric-coordinator; nothing moves until the owner has marked each
row and the tooling of [company-stores.md](company-stores.md) has landed. Names only,
never values.

**Read from**, on 2026-10-15: the coordinator's own store (`fabric-secrets store names`)
and its mirrors of the 33 children's stores (entry file names at each mirror's head);
who reads each name, from `git grep` over `tools/`, `runtime/`, `bin/` and
`projects/registry.json`. A child's own entries newer than its mirror are not seen.

The two company stores: **blueteam** (the operator, `BlueTeam-OU/agent-fabric-secrets`)
and **gzapi** (`gzapi-org/agent-fabric-secrets`), both private and empty. **personal** has
no store and nothing is proposed for it.

## Proposed to move

| Name | Held today by | Proposed home | Why | Owner |
|---|---|---|---|---|
| `CLAUDE_ACCOUNT_<slug>` (2) | coordinator | blueteam | the company's Claude subscriptions; `template-set`/`assign` (ADR-031) read them | |
| `CLAUDE_APIKEY_<slug>` (2) | coordinator | blueteam | the company's API credit on those accounts; the coordinator's alone today, by the owner's word of 2026-10-12 — a move keeps it so (no grants) | |
| `CLAUDE_ASSIGNED_<id>` (26) | coordinator | blueteam | the record of which template each agent got (sha prefix); travels with the templates | |
| `CODEX_ASSIGNED_<id>` (26) | coordinator | blueteam | the same record for the Codex sign-in | |
| `OPENAI_ADMIN_KEY` | coordinator | blueteam | mints every agent's `OPENAI_API_KEY` (`provision issue-key openai`) | |
| `OPENROUTER_PROVISIONING_KEY` | coordinator | blueteam | mints every agent's `OPENROUTER_API_KEY` | |
| `CODEX_CHATGPT_ACCESS_TOKEN`, `CODEX_CHATGPT_ACCOUNT_ID` | coordinator and 25 children | blueteam (source); each agent keeps its applied copy | the company's ChatGPT team sign-in, the same for every agent | |
| `GH_TOKEN`, `CLAUDE_BRIDGE_AUTH_TOKEN`, `GIT_USER_NAME`, `GIT_USER_EMAIL`, `SSH_PRIVATE_KEY`, `SSH_PUBLIC_KEY` | coordinator and 25 children | blueteam (source); each agent keeps its applied copy, granted `all` | `provision share`'s allowlist: the coordinator's own value is the source today, and would die with its key | |
| `BLUETEAM_DEPLOY_HOST`, `BLUETEAM_DEPLOY_USER`, `BLUETEAM_DEPLOY_PASSWORD` | edge-hosting (set by itself, 2026-10-11) | blueteam, granted edge-hosting | the company's deploy target, not the agent's own; a second holder of the role would need it | |

## Proposed to stay in each agent's own store

| Name | Why |
|---|---|
| `AGENT_LOGIN`, `AGENT_HOST` | who the store is (sync's exit 3) |
| `CLAUDE_CODE_OAUTH_TOKEN` | this login's assigned account; put from a template, applied per login |
| `OPENAI_API_KEY`, `OPENROUTER_API_KEY` | one per login by design, for per-agent spend |
| `FABRIC_CONTROL_SIGNING_KEY` | the host operator's own signing key (ADR-029) |
| `GZAPP_PORT_OFFSET` (11) | a per-login value of gzapp's, not a credential |
| `recovery/<id>.key` | each agent's own recovery copy (rule 6) |

## The owner's call

| Name | Question |
|---|---|
| `SERPAPI_API_KEY` (3), `BRAVE_SEARCH_API_KEY` (3) | the language-culture logins' search keys: theirs (stay), the operator's (blueteam), or for gzapi's work (gzapi)? |
| `GIT_SIGNING_KEY`, `GIT_GPG_PROGRAM` (coordinator and 25) | the shared signing key ADR-057 retires: sync still sets `commit.gpgsign` from it. Retire rather than move, once every account is read back signing with its own key — not checked here |
| `AGENT_FABRIC_READ_TOKEN` (coordinator only) | nothing in the tree reads it: remove? |
| gzapi's own credentials | none is in any store today. gzapp's Doppler service token (project `gzapp-backend`) lives in each account's `~/.doppler`, outside the fabric (ADR-038 §7): does gzapi want it in its store? |

## After the review

A holder runs, per approved row: `company import` (from its own store) or `company set`,
then `company grant` and `company put`, then `fabric-ctl all secrets-sync`, and reads back
`sync --status` on one account per grant. An agent's own copy of a moved shared name stays
where it is: only its source changes. The coordinator's own entries are removed last, by
`store rm`, once the company store is read back.

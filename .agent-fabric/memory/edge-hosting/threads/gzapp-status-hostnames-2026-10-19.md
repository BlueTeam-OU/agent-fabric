---
role: "edge-hosting"
class: threads
topic: "gzapp-status-hostnames-2026-10-19"
description: "gzapp status page: paused on 2026-10-25 (cron cleared, status.gzapp.ge detached), why status.gzapi.ge answers 522, and the exact way back"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 00f5aef07594b067
---

## gzapp status page: paused on 2026-10-25 (cron cleared, status.gzapp.ge detached), why status.gzapi.ge answers 522, and the exact way back

On 2026-10-25 at about 15:20Z, the owner chose option B in my own session, so the gzapp-status Worker is paused. Its cron was cleared and its only custom domain, status.gzapp.ge, was detached. The script and its D1 database are untouched. This closed job j17 (REQUEST 01a154a8; done REPLY 01a1737c-7a45).

After the detach, status.gzapp.ge falls through the wildcard CNAME `*.gzapp.ge` to the apex origin and answers Cloudflare 521.

status.gzapi.ge answers 522. The cause is DNS, not an outage: the wildcard CNAME `*.gzapi.ge` points to gzapi.ge, and gzapi.ge points to the Pages project gzapi-ge.pages.dev, which does not hold that hostname. The migration to the hostname that wrangler.toml names was never carried out on the account. The owner declined to attach it for now (j21, REQUEST 01a17375 from devex-tooling).

The token is account-owned and named gzapp-edge-hosting-status-worker. It expires 2026-11-01T22:59Z. Its scope:
- Workers Scripts Write.
- gzapp.ge: Workers Routes Write and DNS Write.
- gzapi.ge: DNS Read only.

Attaching gzapi.ge needs DNS Edit and Workers Routes Edit added on gzapi.ge first.

**Why:** the owner's B choice, given in session. The token was created by the owner in the dashboard, since no route exists for one agent's token to reach another's store (architect-cto-01 REPLY 01a171f5).

**How to apply:** the way back is two API calls:
1. `PUT /accounts/{A}/workers/domains` with hostname status.gzapp.ge, zone gzapp.ge, service gzapp-status, environment production.
2. `PUT .../workers/scripts/gzapp-status/schedules` with `[{"cron":"* * * * *"}]`.

Never use `wrangler deploy` as the way back: the committed config attaches status.gzapi.ge instead. The DELETE on a Workers domain returns an empty body, so don't parse it as JSON. Related: [[cloudflare-worker-has-no-pause]], [[publish-needs-owner-word-in-session]].

*References: cloudflare-worker-has-no-pause, publish-needs-owner-word-in-session*

*Observed 2026-10-25 (edge-hosting)*

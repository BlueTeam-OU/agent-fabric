---
role: "edge-hosting"
class: domain
topic: "cloudflare-worker-has-no-pause"
description: "A Cloudflare Worker has no pause switch: the reversible ways to suspend one, what visitors see under each, and why a redeploy may not undo them"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a1fcf2ffe4794a7a
---

## A Cloudflare Worker has no pause switch: the reversible ways to suspend one, what visitors see under each, and why a redeploy may not undo them

A Cloudflare Worker has no "pause" or "suspend" state. So a request to pause one is really a choice between different visitor effects, and the person who asked has to make it before anything changes:
- **Stop its work, keep it serving.** Clear the cron triggers (`[triggers] crons = []`, or the schedules API). The Worker still answers requests, but anything it computes on a schedule goes stale.
- **Stop it serving.** Detach its custom domains and routes, and disable its workers.dev subdomain. Visitors then get a Cloudflare error page or no answer. The script, its bindings and its data (D1, KV) stay, so this is reversible.
- **Serve something else.** A maintenance response is a new deploy of different code, not a pause. Its content belongs to the page's content owner.

Deleting the script is not a pause. It takes the Worker's version history and binding wiring with it.

**Why:** two requests on 2026-10-19 asked to pause gzapp's status-page Worker. The first already listed these options and warned they differ in what visitors see; the reply to the second set them out as A, B and C.

**How to apply:** ask which visitor effect is wanted before acting, and write down the exact way back first. A plain `wrangler deploy` restores whatever the committed wrangler.toml says now: its routes, custom domains and crons. That can differ from what was live, for example when the config names a hostname that hasn't been migrated yet. So when the committed config and the live state disagree, the way back is the specific API call, not a redeploy. Related: [[gzapp-status-hostnames-2026-10-19]], [[publish-needs-owner-word-in-session]].

*References: gzapp-status-hostnames-2026-10-19, publish-needs-owner-word-in-session*

*Observed 2026-10-24 (edge-hosting)*

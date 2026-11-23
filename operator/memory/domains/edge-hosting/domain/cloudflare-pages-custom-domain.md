---
role: "edge-hosting"
class: domain
description: "Cloudflare Pages custom-domain cutover: attach via API, then swap the DNS record"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 5ca5584f094e684c
  - 8071e97ff37d8326
  - b30fb2698f738c2f
  - e5b78bfd41616047
  - f5c9486f0ee50f13
---

## Cloudflare Pages custom-domain cutover: attach via API, then swap the DNS record

> Learned outside this system; it describes the field, not our implementation.

Moving a domain from an external origin onto Cloudflare Pages is two separate steps, not one: (1) attach the custom domain to the Pages project via the API, which starts it in status `initializing` and only later `pending`/serving — attaching does not itself change DNS; (2) separately delete the old origin A record and replace it with a proxied (orange-cloud) CNAME to the project's `<project>.pages.dev` subdomain, including at the apex via CNAME flattening. Both the apex and any `www` subdomain need their own custom-domain attachment. Once both steps are done, full cutover (DNS propagation + Pages serving live) completed in well under 5 minutes in practice, passing through the 522/523 sequence described in the origin-errors claim before settling to 200.

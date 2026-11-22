---
role: "edge-hosting"
class: domain
description: Cloudflare 521 vs 522/523 — what each error class actually means
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 00a063e3968192c7
  - 1ee3e8a79c64f826
  - 270e73e4eadb1130
  - e8d02832634bc1ad
  - f5c9486f0ee50f13
---

## Cloudflare 521 vs 522/523 — what each error class actually means

> Learned outside this system; it describes the field, not our implementation.

On a domain proxied through Cloudflare, HTTP 521 ("Web Server Is Down") means Cloudflare's edge reached the zone but the origin refused the TCP connection outright — a real outage or a DNS record still pointing at a dead/wrong origin. 522 ("connection timed out") and 523 ("origin unreachable") are different: they showed up specifically in the first ~20-45 seconds right after a first-ever deploy to a brand-new Cloudflare Pages project and after attaching a custom domain, then resolved to 200 on their own without any further action once Cloudflare's internal propagation finished. A verification script run immediately after a first deploy or a custom-domain cutover should expect and retry through this sequence rather than treating an initial 522/523 as a failed deploy; a 521 that persists past that window is a genuine origin problem, not propagation.

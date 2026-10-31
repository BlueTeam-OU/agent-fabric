---
role: "edge-hosting"
class: threads
description: "Open gzapp edge item — any CSP served for admin_web/advertiser_web must allow the Stream media host in connect-src and media-src, plus blob:"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 33cc97c77c518c7a
---

## Open gzapp edge item — any CSP served for admin_web/advertiser_web must allow the Stream media host in connect-src and media-src, plus blob:

Project gzapp. architect-cto-01 ruled (01a0e31e) that video creatives play through a bundled HLS engine (hls.js) where the browser has no native HLS. The engine fetches manifests and segments with XHR/fetch. So if the edge ever serves a Content-Security-Policy for admin_web or advertiser_web, it needs the Stream delivery host in `connect-src` as well as `media-src`, and `blob:` in `media-src` (MediaSource). web-dev-01 sent this to edge-hosting (01a0e322, 2026-09-27), and nothing is asked now.

State as of 2026-10-17: `git grep` on gzapp origin/main finds no CSP or connect-src anywhere, so there is nothing to do yet.

**How to apply:** before adding or changing a CSP (a header at the edge or a meta tag) for those apps, include these sources and tell web-dev. Drop this thread once a CSP that has them is on main.

*Observed 2026-10-17 (edge-hosting)*

---
role: "edge-hosting"
class: domain
topic: "long-max-age-unversioned-asset"
description: "Before publishing a change to a CSS/JS file, read the host's Cache-Control for it; a long max-age on an unversioned URL serves new pages with the old asset"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9ff987922f8ed20f
---

## Before publishing a change to a CSS/JS file, read the host's Cache-Control for it; a long max-age on an unversioned URL serves new pages with the old asset

If a static host sends a long `Cache-Control: max-age` for an asset and the pages link it by a fixed URL, then a change to that asset is not seen at once. Every visitor who already has it cached gets the new HTML with the old CSS/JS until max-age runs out. The pages look broken, and the served bytes still match the build. When the max-age is long, this is a defect, not the harmless "client cache may still show it" note.

**Why:** blueteam.ee, 2026-10-30. The 19858f4 upload changed site.css, and I reported "a browser cache may still show the old site.css" as expected (01a18cec). The host sends `max-age=604800` (a week) for assets/css/site.css. So returning visitors saw the new pages with the old stylesheet. brand-comms then shipped content-hash links, 61e5168 (`../blueteam.ee/src/lib/asset.ts`, `?v=<hash>`), and that is now the executable fix for that site.

**How to apply:** when a change touches an asset, curl -I the public URL for its Cache-Control before the upload, and check that the pages link it with a content version. If the max-age is long and the link is unversioned, raise it with the page's owning role (web-dev or brand-comms) before going live, not after. Name the max-age when you report what a client cache can still show. After the upload, check that the versioned URL the pages link answers 200 with the built bytes. Related: [[publish-needs-owner-word-in-session]].

*References: publish-needs-owner-word-in-session*

*Observed 2026-10-31 (edge-hosting)*

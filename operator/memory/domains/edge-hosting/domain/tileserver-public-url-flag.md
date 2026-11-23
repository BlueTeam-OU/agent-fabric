---
role: "edge-hosting"
class: domain
description: "TileServer-GL's --public_url flag rewrites embedded URLs so a fronting proxy needs no body-rewriting logic"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 9a882ab48d6e52e3
  - b4f56f3480c6daaa
---

## TileServer-GL's --public_url flag rewrites embedded URLs so a fronting proxy needs no body-rewriting logic

TileServer-GL exposes a `--public_url <url>` CLI flag documented as enabling "exposing the server on subpaths, not necessarily the root of the domain." Set at startup, it rewrites every absolute URL TileServer-GL embeds in the documents it serves — `style.json`'s `glyphs`/`sources` fields, TileJSON responses, font/glyph URLs — to the specified base URL, rather than the tileserver's own internal bind address. A proxy sitting in front of it (or a CDN/edge cache addressing it under a public hostname) can therefore get correctly-addressed public URLs in every served document for free, by starting the upstream tileserver with `--public_url` pointed at the proxy's public address, instead of implementing response-body URL rewriting on the proxy side.

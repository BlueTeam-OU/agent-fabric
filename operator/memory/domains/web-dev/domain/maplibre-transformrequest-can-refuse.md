---
role: "web-dev"
class: domain
topic: "maplibre-transformrequest-can-refuse"
description: "How a MapLibre map refuses to send a request (ADR-073 r15) — transformRequest returning a rejected Promise; returning undefined still sends"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 93eda90bd50626c9
---

## How a MapLibre map refuses to send a request (ADR-073 r15) — transformRequest returning a rejected Promise; returning undefined still sends

In maplibre-gl 6.16.0 `RequestManager.transformRequest` returns
`fn(url, type) || {url}`, so a transform returning `undefined` (or a
`{url}` without headers) still sends the request, tokenless. Every
caller — style (`ui/map.ts`, `style/style.ts`), tilejson
(`source/load_tilejson.ts`), vector tiles, sprites
(`style/load_sprite.ts`), glyphs, images — `await`s the result before
fetching, so returning a REJECTED Promise refuses the request before
anything leaves the browser; the failure surfaces as a map `error`
event. Read in `node_modules/.pnpm/maplibre-gl@6.16.0/.../src/`
2026-11-10, for ADR-073 §5 r15 (no style/tile/sprite request to an
origin other than the tile service's). Re-read on a MapLibre bump. See
[[tile-default-wording-adr034-dev-fallback]].

Confirmed in Chromium (Playwright, 2026-11-10, j27): a style with a
foreign-origin sprite and vector source, transform rejecting non-own
origins — nine `error` events, zero requests to the foreign origin,
own-origin tiles still fetched by the worker (control: they show in the
network log). Shipped as `TileRequestRefusedError` in
`packages/web-shared/src/map/tileToken.ts` (commit 4eda79308).

*References: tile-default-wording-adr034-dev-fallback*

*Observed 2026-11-10 (web-dev)*

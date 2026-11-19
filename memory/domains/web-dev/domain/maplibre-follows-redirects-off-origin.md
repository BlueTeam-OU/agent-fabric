---
role: "web-dev"
class: domain
topic: "maplibre-follows-redirects-off-origin"
description: "MapLibre 6.16 follows a 3xx from an admitted origin to any other host, tokenless; transformRequest cannot set a redirect mode; only addProtocol + own fetch(redirect:'error') can refuse"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 00b2608bbdb8e6dd
---

## MapLibre 6.16 follows a 3xx from an admitted origin to any other host, tokenless; transformRequest cannot set a redirect mode; only addProtocol + own fetch(redirect:'error') can refuse

Measured in Chromium with maplibre-gl 6.16.0 (gzapp j31, 2026-11-10, answering architect-cto-01's 01a1c73a; reply 01a1c73e):

- The tile origin answered 302 to a counting third host. MapLibre followed it for the style document, the sprite JSON and PNG, a GeoJSON source and raster tiles, on both the main thread and the worker. The browser dropped `Authorization` on the cross-origin hop, but the request still left. `transformRequest` sees only the URL that was asked for, so it admitted every one, and no refusal fired.
- Source (`src/util/ajax.ts`): `RequestParameters` has no `redirect` field. `makeFetchRequest` builds `new Request(…)` without one, so the default `follow` applies. The XHR fallback and the HTMLImageElement image path always follow.
- Control on the same page: `fetch(url, {redirect: "error"})` rejects, and `redirect: "manual"` gives an `opaqueredirect`. Neither reached the third host.
- The only client-side refusal, not yet built or measured: `transformRequest` rewrites the URL to a custom scheme, and an `addProtocol` handler does its own fetch with `redirect: "error"`. A custom scheme also makes `getImage` skip the HTMLImageElement path.

An origin check on the requested URL is therefore not an origin check on the request. Related: [[maplibre-transformrequest-can-refuse]], [[standalone-map-harness-browser-check]].

*References: maplibre-transformrequest-can-refuse, standalone-map-harness-browser-check*

*Observed 2026-11-10 (web-dev)*

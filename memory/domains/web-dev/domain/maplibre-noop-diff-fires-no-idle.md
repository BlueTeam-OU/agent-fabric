---
role: "web-dev"
class: domain
topic: "maplibre-noop-diff-fires-no-idle"
description: A MapLibre setStyle diff to an identical document fires no idle/render; a state machine waiting on idle after a style swap hangs until its deadline
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 83bba43b6b1183e3
---

## A MapLibre setStyle diff to an identical document fires no idle/render; a state machine waiting on idle after a style swap hangs until its deadline

MapLibre GL 6.16.0 `Map._updateDiff` calls `_update(true)` only when `style.setState(...)` returns true. A diffed `setStyle` to a document that changes nothing (the same style under another URL) therefore makes no render and fires no `idle`, `styledata` or `style.load`. No event marks the end of such a diff.

Seen in Chromium on gzapp #1250 (2026-11-11): admin MapView and web-shared MapCanvas ended a swap's load on `idle`, so an identical-document palette switch sat in loading until `BASEMAP_DEADLINE_MS` and then drew map-unavailable over a working map. The fix was to build a new map for every style change (`load` always fires), opened at the last `onMoveEnd` camera.

A jsdom mock cannot show it: the mock fires whatever events the test chooses. Reproduce with a fake tile service that serves the same JSON at both style URLs ([[standalone-map-harness-browser-check]]).

*References: standalone-map-harness-browser-check*

*Observed 2026-11-11 (web-dev)*

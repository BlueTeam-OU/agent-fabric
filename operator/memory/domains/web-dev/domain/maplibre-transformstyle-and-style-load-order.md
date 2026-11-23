---
role: "web-dev"
class: domain
topic: "maplibre-transformstyle-and-style-load-order"
description: "MapLibre 6.16: a constructor transformStyle holds every swap away from a never-loaded style forever; style.load fires AFTER setState/_load requested the document's sources and sprite; a diff does not abort the map's first load"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - a346b4073cce55e3
---

## MapLibre 6.16: a constructor transformStyle holds every swap away from a never-loaded style forever; style.load fires AFTER setState/_load requested the document's sources and sprite; a diff does not abort the map's first load

Read in maplibre-gl 6.16.0 `src/ui/map.ts` and `src/style/style.ts`, confirmed in Chromium with controls (gzapp #1244, 2026-11-10):

- `transformStyle` given at construction becomes `_transformStyle`, merged into EVERY later `setStyle`. With it set, `_updateStyle` does `if (options.transformStyle && this.style && !this.style._loaded) { this.style.once('style.load', …); return; }` — a swap away from a style whose document 404'd or hung never lands. react-maplibre passes it to the constructor only. So: no constructor `transformStyle` (review F1).
- `style.load` fires at the END of `Style.setState` / `Style._load`, after the diff operations ran `addSource` (TileJSON/GeoJSON `transformRequest(…, "Source")`, synchronous) and `setSprite` (`SpriteJSON`/`SpriteImage`). Tiles and glyphs come after. Anything keyed on "document applied" must treat Style/Source/Sprite*/Image requests as the incoming style's (review F3).
- `_diffStyle` aborts an earlier DIFF request, not the map's first `Style.loadURL`; `Map.remove()` → `setStyle(null)` → `Style._remove` aborts it. A swap during the first load can let that document land afterwards unless the map is rebuilt (review F2).
- A diff with zero operations fires no `style.load`.
- Node/WHATWG: an opaque origin (`data:`, custom scheme) serialises as `"null"`; `new URL(path, "null")` throws; two opaque URLs compare equal as strings. `blob:` carries its creator's origin.

The mocked `<Map>` suite saw none of these; each was found by the review class reading the locked source. Related: [[maplibre-transformrequest-can-refuse]], [[standalone-map-harness-browser-check]].

*References: maplibre-transformrequest-can-refuse, standalone-map-harness-browser-check*

*Observed 2026-11-10 (web-dev)*

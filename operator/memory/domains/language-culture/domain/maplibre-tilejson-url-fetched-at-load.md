---
role: "language-culture"
class: domain
topic: "maplibre-tilejson-url-fetched-at-load"
description: "In a spec check that relies on a layer minzoom to delay a request, \"a source on origin X\" reads two ways (TileJSON url vs tiles URLs)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - f3161ade3c0a9268
---

## In a spec check that relies on a layer minzoom to delay a request, "a source on origin X" reads two ways (TileJSON url vs tiles URLs)

MapLibre requests a source's TileJSON `url` when the style loads, whatever its layers' `minzoom`. It requests the source's `tiles` URLs only once a layer that uses the source is visible at the current zoom. So a test step written as "a source on a third origin, used only by a layer with a minzoom above the start zoom" reads two ways, and only the `tiles` reading delays the request until the zoom. The TileJSON reading fails at load instead. Found in the admin map note's A20 (design/2026-11-10-admin-map-unavailable-state.md, commit 53f723512). It was raised with ux-designer as a condition for them to word (REPLY 01a1c8b9, 2026-11-11), and per [[condition-wording-raised-then-written-verbatim]] it was not rewritten.

*References: condition-wording-raised-then-written-verbatim*

*Observed 2026-11-11 (language-culture)*

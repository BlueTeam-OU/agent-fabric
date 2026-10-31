---
role: "web-dev"
class: solution
description: A MapLibre paint colour taken from a gzapp design token must be converted to sRGB first — the tokens are OKLCH and MapLibre rejects the layer
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f5d8d5a2bd86cd5
---

## A MapLibre paint colour taken from a gzapp design token must be converted to sRGB first — the tokens are OKLCH and MapLibre rejects the layer

gzapp's design tokens (packages/web-shared/src/design-tokens/tokens.css) resolve to
`oklch(...)`. MapLibre paint properties accept only CSS Color 3 forms: handed
`oklch(0.55 0.18 30)` it throws "line-color: color expected" and admin_web's MapView
reports it as "the basemap failed to load". jsdom resolves no token, so a Vitest suite
cannot see this; only a real browser can (found driving PR #1097's restriction editor).

The fix in `apps/admin_web/src/features/stops/tokenColor.ts` paints the token on a 1×1
canvas and reads the pixel back as rgba, so the browser does the colour-space
conversion and the token stays the single source. Re-read it on palette change
(useResolvedTheme as the memo dependency). Any new paint layer (line, fill, circle)
fed from a token needs the same conversion. Markers styled with Tailwind token classes
are unaffected (CSS handles OKLCH).

*Observed 2026-10-10 (web-dev)*

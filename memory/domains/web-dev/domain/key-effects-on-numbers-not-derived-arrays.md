---
role: "web-dev"
class: domain
topic: "key-effects-on-numbers-not-derived-arrays"
description: An effect whose dependency is an array or object rebuilt in render runs on every render; key it on the primitives.
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 2b8cbf18d56c6e43
---

## An effect whose dependency is an array or object rebuilt in render runs on every render; key it on the primitives.

A `useEffect` whose dependency is a value built during render (`[lng, lat]`, `{...}`) runs on EVERY
render, not only when the value changes. In advertiser_web's LocationField the pin's keep-in-view effect depended
on such an array; it was harmless until a search pick started moving the map away from the pin, and then any parent
render eased the map back (#1257 review F1, fixed in 4a7cd97a1 by depending on `point?.[0]`, `point?.[1]`).

**Why:** the bug only shows once something else changes what the effect does, so a review of the effect alone misses it.

**How to apply:** when adding or reviewing an effect, check whether each dependency is a fresh object built in render;
depend on its primitives (or memoise it). The test that holds it: re-render from the parent with the inputs unchanged
and assert the effect's side effect count did not grow.

*Observed 2026-11-14 (web-dev)*

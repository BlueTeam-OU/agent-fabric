---
role: "web-dev"
class: domain
description: "Preventing horizontal overflow from images and long unbreakable heading tokens needs explicit CSS, not just max-width"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 4825c6321fde2edb
  - 69065854023399ba
  - bd36ceafdc2c1f1c
---

## Preventing horizontal overflow from images and long unbreakable heading tokens needs explicit CSS, not just max-width

> Learned outside this system; it describes the field, not our implementation.

Two general CSS techniques worth defaulting to on any responsive web surface: (1) a global image reset of `max-width: 100%` alone is insufficient — without a companion `height: auto`, a width-constrained image keeps its HTML `height` attribute and renders visibly distorted; and (2) a single long unbreakable token in a heading (a product name, proper noun) can force horizontal page overflow at narrow viewports even with normal text wrapping enabled, because `overflow-wrap: break-word`/default wrapping does not break inside a token with no natural break points — `overflow-wrap: anywhere` combined with a `clamp()`-based responsive `font-size` at the narrow breakpoint is what actually prevents the overflow. Both were caught via an automated per-route, per-viewport sweep comparing `scrollWidth` to `clientWidth`, which is a reliable way to catch this class of bug systematically rather than by manual spot-checking.

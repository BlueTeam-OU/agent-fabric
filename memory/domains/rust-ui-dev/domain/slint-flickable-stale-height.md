---
role: "rust-ui-dev"
class: domain
topic: "slint-flickable-stale-height"
description: "in Slint 1.18.1 a VerticalLayout inside a Flickable reads a stale preferred-height right after a change; re-anchor on changed content-height"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 26eaa6b20d36fff3
---

## in Slint 1.18.1 a VerticalLayout inside a Flickable reads a stale preferred-height right after a change; re-anchor on changed content-height

Slint 1.18.1: inside a `Flickable`, a `VerticalLayout`'s `preferred-height` (and so the Flickable's `content-height` bound to it) reads stale -- the padding alone -- right after its children change. Anchoring the view at the newest item from that value lands wrong. Re-anchor in a `changed content-height` handler instead. The Flickable clamps `content-y` to `content-height`; drag scrolling works regardless.

Found building j111's F9 (conversation anchored at newest, #313, 2026-10-19).

Related: [[slint-swipe-in-flickable]] [[slint-flicked-input-only]]

*References: slint-flicked-input-only, slint-swipe-in-flickable*

*Observed 2026-10-24 (rust-ui-dev)*

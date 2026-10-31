---
role: "rust-ui-dev"
class: domain
topic: "slint-software-renderer-round-image"
description: "Slint's software renderer draws an Image square inside a clipped rounded Rectangle; paint the corners with an even-odd Path in the backdrop colour"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - e6499bb887000e34
---

## Slint's software renderer draws an Image square inside a clipped rounded Rectangle; paint the corners with an even-odd Path in the backdrop colour

Slint's software renderer (the desktop build's, `renderer-software`) does not clip an `Image` to a parent's `border-radius` + `clip: true`: a round avatar photo renders square, while a Rectangle child clips fine. Seen rendered under Xvfb, 2026-10-24.

Working fix: overlay a `Path` the image's size with `viewbox 2x2`, `fill-rule: evenodd`, commands `M 0 0 L 2 0 L 2 2 L 0 2 Z M 1 0 A 1 1 0 1 0 1 2 A 1 1 0 1 0 1 0 Z`, filled with the colour behind the avatar (a `backdrop` property each use sets). Needs `software-renderer-path`. The edge comes out anti-aliased. It breaks where the backdrop changes under the avatar (hover state layers), so give such a row a fixed background.

Rendered check: run a scratch test with the `desktop` feature under the display wrapper and dump `Window::take_snapshot()` to RGBA, then convert to PNG. Bound the event loop: a harness that drops `MarkRead` intents spins forever in `take_events`.

InterWeave: `crates/human/ui-slint/ui/app.slint` PhotoCircle, #407 commit c96b404f.

*Observed 2026-10-24 (rust-ui-dev)*

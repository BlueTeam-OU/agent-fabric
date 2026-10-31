---
role: "rust-ui-dev"
class: domain
topic: "slint-royalty-free-attribution"
description: "Meeting the Slint Royalty-free 2.0 attribution duty -- AboutSlint needs an image feature; the download-page badge is the alternative"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 836d036e57220b2b
---

## Meeting the Slint Royalty-free 2.0 attribution duty -- AboutSlint needs an image feature; the download-page badge is the alternative

Slint Royalty-free 2.0 is satisfied either by the AboutSlint widget on an About screen
reachable from the app's top level, or by the Slint attribution badge on the public page
the binaries are downloaded from. With slint default-features off, std-widgets' AboutSlint
fails to compile without an image feature (it draws an embedded SVG logo), so the widget
route adds an SVG rasteriser to the dependency graph and its licence review. A project
that has just ruled on its graph can carry the duty to packaging (the badge) instead; if
no public download page exists when the first binary ships, the widget route returns,
with its feature delta measured under cargo deny first.

*Observed 2026-10-15 (rust-ui-dev)*

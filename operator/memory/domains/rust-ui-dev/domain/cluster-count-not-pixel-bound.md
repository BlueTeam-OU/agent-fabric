---
role: "rust-ui-dev"
class: domain
topic: "cluster-count-not-pixel-bound"
description: "A grapheme-cluster count bounds no drawn size; test layout bounds with wide glyphs (U+FDFD, emoji, CJK, W), not \"x\""
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2df2629505fe254f
---

## A grapheme-cluster count bounds no drawn size; test layout bounds with wide glyphs (U+FDFD, emoji, CJK, W), not "x"

Measured 2026-11-07 (j95, desktop, 200 % text, 360 wide): 2,000 clusters draw 6,824 px for "x", 12,576 for "W"/CJK,
17,501 for emoji and 87,236 for U+FDFD (one code point each). A bound stated in clusters or code points (a cut, a
piece size) holds a pixel bound only for the font and script it was measured with. A layout-bound test whose shapes
are narrow Latin passes while the bound fails (long_message.rs a4_shapes did). Feed it U+FDFD, emoji and CJK.
Related: [[slint-software-renderer-i16-height]] [[slint-testing-tree-omits-clipped]]

*References: slint-software-renderer-i16-height, slint-testing-tree-omits-clipped*

*Observed 2026-11-07 (rust-ui-dev)*

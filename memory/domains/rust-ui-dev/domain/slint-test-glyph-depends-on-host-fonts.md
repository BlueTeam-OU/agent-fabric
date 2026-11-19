---
role: "rust-ui-dev"
class: domain
topic: "slint-test-glyph-depends-on-host-fonts"
description: "A Slint testing-backend test whose premise is a glyph's drawn size (U+FDFD tall, CJK wide) passes here and fails on CI, which lacks the font; use Latin 'W' and assert the premise"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - a6d8ae595d07a876
---

## A Slint testing-backend test whose premise is a glyph's drawn size (U+FDFD tall, CJK wide) passes here and fails on CI, which lacks the font; use Latin 'W' and assert the premise

The Slint testing backend shapes text with the host's system fonts. This
host has Noto Sans Arabic, so 1,960 x U+FDFD drew a link label 10,751 px
tall; GitHub's runner had no such font and drew it short, so the link fitted
the screen and the test (#600, `tab_in_the_reader_keeps_a_link_taller_than_
the_screen`) failed on CI only: the last row cannot be scrolled to the top.

**Why:** a test's premise built from one glyph's size is a fact about the
host's fonts, not the code; it reads green locally and red elsewhere.

**How to apply:** when a test needs something tall or wide, build it from
Latin letters ("W" draws wide in every font with Latin), and ASSERT the
premise (`link.size().height > area.size().height`), so a font that breaks it
fails with that message, not a misleading position. A CI-only red in
ui-slint: check the glyphs first. See [[cluster-count-not-pixel-bound]].

*References: cluster-count-not-pixel-bound*

*Observed 2026-11-09 (rust-ui-dev)*

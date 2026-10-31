---
role: "rust-ui-dev"
class: domain
topic: "slint-styledtext-links"
description: "Rendering rich message text in Slint -- StyledText links are pointer-only and from_markdown is a second parser; draw from your own tree, links as separate controls"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3e26e4a9e519cb42
---

## Rendering rich message text in Slint -- StyledText links are pointer-only and from_markdown is a second parser; draw from your own tree, links as separate controls

As of Slint 1.18.1 the only rich-text element is StyledText. Its links answer a pointer
click only: they are not focusable and are not separate accessibility nodes, so a link
drawn inside it is unreachable by keyboard and screen reader. StyledText::from_markdown is
Slint's own pulldown-cmark-based parser (honours <u> and <font>), not CommonMark.

So for remote-derived text: parse once with the product's own validated parser, draw each
block from that tree as plain text (no second parser, no escaping function as a security
boundary -- a security ruling refused re-serialising to markdown for Slint), and render each
allowed link as a separate focusable button after the body, labelled with its full
destination, acting only on activation. Re-check both facts on a Slint bump.

*Observed 2026-10-15 (rust-ui-dev)*

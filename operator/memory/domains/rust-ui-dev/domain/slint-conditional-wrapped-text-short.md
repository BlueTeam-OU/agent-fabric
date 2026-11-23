---
role: "rust-ui-dev"
class: domain
topic: "slint-conditional-wrapped-text-short"
description: "Slint 1.18 measures a wrapped Text inside conditional/repeated layouts a line short; give each such Text min-height self.preferred-height"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 80b475c40b85b0a6
---

## Slint 1.18 measures a wrapped Text inside conditional/repeated layouts a line short; give each such Text min-height self.preferred-height

In Slint 1.18, a word- or char-wrapped `Text` inside an `if cond: VerticalLayout {}` (or a `for`
repeater) is measured as if its lines did not wrap. The layout info that the enclosing layouts and a
`preferred-height: body.preferred-height` binding read comes out one line short per wrapped line,
while the Text draws at its real width and wraps. The container is then shorter than what it draws:
with `clip`, its end is cut off; in a list, the next row covers it.

Seen 2026-10-26 on #453's follow-up branch: ProposalCard's PeerId (char-wrap) and its notes
(word-wrap). Measured with a probe Text showing `body.preferred-height`: it read 389 where the
card's content needs 405, at 386 px wide.

What did not fix it:
- an explicit `width: parent.width` on the Text (a binding loop);
- word-wrap with zero-width spaces;
- wrapping the conditional layout in a Rectangle;
- extracting it into a component (it fixed one slot and broke another);
- more frames or a resize.

What did: `min-height: self.preferred-height;` on every wrapped Text in the container. A Text's own
preferred height comes from its own drawn width.

**How to apply:**
- Any wrapped Text under a conditional or repeated layout whose container sizes from layout info
  gets that line.
- The test that catches it compares where the element ends (`absolute_position` + `size`) against
  its container and the next row, at a phone's width (320-420 px), with and without 200 % text.
- A test that only checks that a control is "in the tree" passes by luck.

*Observed 2026-10-26 (rust-ui-dev)*

---
role: "ux-designer"
class: workflow
topic: "restated-conditions-quoted-verbatim"
description: "Where a review record or another section restates a spec's condition or a string, quote it word for word with its locator; a paraphrase narrows the condition or makes a second version of the text"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc74966b665f7793
---

## Where a review record or another section restates a spec's condition or a string, quote it word for word with its locator; a paraphrase narrows the condition or makes a second version of the text

A restatement drifts from what it restates, and a wording pass on the
restatement drifts further, because the editor sees only the copy:
- a device-review cell said "5.2 asks that a screen reader read the line
  after the circle"; 5.2's condition names no assistive technology and
  also governs Tab order, so the cell narrowed it (#462 review, F4);
- a spec section paraphrased a string's text ("so it cannot be accepted
  yet"), which made a second version of one string (#491,
  language-culture-en's second pass).
**Why:** InterWeave, 2026-10-26/27; the #457 record whose two 5.2
quotations were verbatim passed the same check untouched.
**How to apply:** in a review record's "spec says" cell and in any
section that refers to a string, paste the condition or text verbatim
with its line or section; if it must be shortened, cite it and say what
is left out instead of rewording it. Tell language-culture that quoted
spans are not theirs to reword.
Related: [[wording-pass-keeps-conditions]], [[verdict-per-condition-walked]]

*References: verdict-per-condition-walked, wording-pass-keeps-conditions*

*Anchors: `interweave:design/2026-10-26-photo-step-review.md::Focus and speech in the photo step`*

*Observed 2026-10-31 (ux-designer)*

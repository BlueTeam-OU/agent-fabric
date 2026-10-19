---
role: "ux-designer"
class: domain
topic: "wording-pass-keeps-conditions"
description: "Read every language/English pass on a spec as a diff for meaning: a reworded if/else can drop a case"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - b19535ad392eccd6
---

## Read every language/English pass on a spec as a diff for meaning: a reworded if/else can drop a case

A copy-edit of a specification can change behaviour. Read the diff of
each English pass for its conditions, and ask the editor to keep every
"if ... else" whole.

**Why:** on InterWeave #286 (2026-10-16), language-culture-en's pass
turned "its first control if the row is on screen, else as after a
removal" into "if on screen ... If the row was removed ...". That
dropped the row still listed but scrolled off screen. Round 6's review
caught it as a P2; nobody had read the pass for meaning.

**How to apply:** when folding a wording branch, run
`git diff <mine> <theirs>` and check every changed sentence that holds
a condition, a quantity or a list of cases. In the request, name the
rules whose wording decides behaviour (for example a definition such as
"first control").

Related: [[focus-table-in-spec]]

*References: focus-table-in-spec*

*Observed 2026-10-17 (ux-designer)*

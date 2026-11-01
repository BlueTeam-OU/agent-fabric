---
role: "language-culture"
class: workflow
topic: "labels-key-has-a-design-row"
description: "in InterWeave a labels.rs key usually also has a row in a design note's string table; finalise both as one text, and name the other when they differ"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e19565ebc9f7d0bc
---

## in InterWeave a labels.rs key usually also has a row in a design note's string table; finalise both as one text, and name the other when they differ

In InterWeave, two roles can ask me for the same key's text. rust-ui-dev
owns `crates/human/ui-model/src/labels.rs`, and ux-designer owns the
string table (s9 or s10) of a note under `design/`. Three times in W43,
one key reached me from both:
- IdActiveElsewhere: I answered rust-ui-dev-02 first. Minutes later
  ux-designer-01 asked for it beside IdR1NewKeys, and on that page my
  text contradicted the next paragraph. I had to send a replacement
  REPLY that named the message it replaced.
- CardPhotoNotUsed: my final text for #414 differed from the design row.
  I sent an OBSERVATION to the row's owner, and did not edit their row.
- CardUndoHint: finalised on #416 (design) first, then confirmed on
  #414 (code) as the same text.
Verified 2026-10-25 on InterWeave origin/main: the two files hold the
same final text for CardUndoHint, CardPhotoNotUsed, IdActiveElsewhere
and KeyDirUnsafePath.

**Why:** a text worded for one file alone is checked against only that
file's context. The design note has the neighbours and the states, and
the code has the doc comment. Reading only one of them is how the
IdActiveElsewhere text contradicted its page.

**How to apply:** before finalising a labels.rs key, `git grep` its name
in `design/` and read its row and the page around it. Before finalising
a design row, look for the key in labels.rs. Send one text. If you change
a text already sent, the REPLY names the message or commit it replaces,
and says "do not fold" for a for/ commit that is now wrong.

Related: [[dictionary-value-has-readers-outside-the-dictionary]], [[name-the-pushed-commit]]

*References: dictionary-value-has-readers-outside-the-dictionary, name-the-pushed-commit*

*Anchors: `interweave:crates/human/ui-model/src/labels.rs::CardUndoHint`, `interweave:design/2026-10-21-contact-cards.md::CardUndoHint`*

*Observed 2026-10-25 (language-culture)*

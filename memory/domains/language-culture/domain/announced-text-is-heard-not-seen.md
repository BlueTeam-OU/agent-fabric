---
role: "language-culture"
class: domain
topic: "announced-text-is-heard-not-seen"
description: "a screen-reader-only text is heard in a sequence, so place things by reading order and name them in the words the screen reader itself uses"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0742a5568f87334e
---

## a screen-reader-only text is heard in a sequence, so place things by reading order and name them in the words the screen reader itself uses

A text that is only announced (an accessible description, a live region,
a notice read before focus moves) has no page around it. Its listener
hears it between two other things. Four traps from InterWeave, W43:
- **What comes next.** PeerRowGone is read just before the next row's
  label. "That address" was heard as the next row, so the text says
  "the address you acted on" or "the address that was focused".
- **Where things are drawn.** CardUndoHint first said Undo was "just
  above the box where you type". When network access is withheld, no
  composer is drawn. "Bottom" and "last item" were heard as the newest
  message. The final text places Undo by reading order: "after all the
  messages in this conversation". It is true in every state.
- **The screen reader's own words.** "Focused" is the word a screen
  reader says as focus moves, so its listener knows it.
- **Ellipsis.** A screen reader reads "…" in different ways. A line of
  full sentences beside a progress mark takes a full stop
  (TrustStepWaiting). A short in-progress label keeps "…" ("Adding…"),
  as every other in-progress label in labels.rs does.

**Why:** a writer checks an announced text on the screen they picture.
The listener has only the sequence, and what is drawn changes with the
state.

**How to apply:** for each announced text, write down what is heard just
before it and just after it. Then check each pointing word ("that", "it",
"here") against what comes after it. Place a control by reading order,
never by a visual landmark. Give the cold reader the sequence of what is
heard, not only the text.

Related: [[key-value-true-in-every-state]], [[instruction-doable-in-reader-situation]]

*References: instruction-doable-in-reader-situation, key-value-true-in-every-state*

*Observed 2026-10-25 (language-culture)*

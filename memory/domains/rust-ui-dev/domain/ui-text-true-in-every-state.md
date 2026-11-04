---
role: "rust-ui-dev"
class: domain
topic: "ui-text-true-in-every-state"
description: "A UI string (placeholder included) must be true in every state and case it shows in: tense before the act, no claim of a step that never happened, location by reading order"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c8576b4f4e5a48a6
---

## A UI string (placeholder included) must be true in every state and case it shows in: tense before the act, no claim of a step that never happened, location by reading order

Five placeholder drafts in one week (InterWeave contact cards, 2026-10-24..25) were changed by
the copy owner for the same class of fault: the text was true in the state the drafter pictured
and false in another state the same key shows in.
- Tense: a change line shown BEFORE the person confirms ("Current photo removed") reads as
  already done; it became "Your contact's photo will be removed." A past participle belongs to
  the confirmation after the act.
- A step that never happened: "The card's photo could not be shown" was false — the photo is
  never shown before Accept; "could not be used" is true in both failing cases (undecodable,
  too large).
- Location: "above the box where you type" pointed at nothing in the state with no composer;
  name the place by reading order.
- Words colliding with a nearby destructive action: "Delete your changes?" was read as deleting
  the card beside "Delete contact"; "Discard" was a word the app used nowhere else. The app's
  own verb for leaving a view ("Close without saving") won.
- A label read beside every status of its row: "You shared your card" contradicted
  "Not sent" beside it; "Your contact card" claims nothing and lets the status say how far it got.
- An instruction that presumes a thing exists: "send from one of those conversations" pointed at
  conversations the identity in front may not have; "if you have one" claims nothing.
- Joins in code: when a fragment becomes a whole sentence ("The card includes your photo."),
  the code joining it (", ") and appending (". ") must change too, or the reader hears
  "..., The card includes your photo.. Sent". Compose spoken labels from whole sentences.
- Referents: "That must not happen" had two antecedents; name the rule instead.

**How to apply:** before sending a placeholder to the copy owner, list every state and case the
key renders in (from the model, not the mockup) and check the draft against each: tense
relative to the act, what has actually happened to the object, what is drawn there, and which
other labels sit on the same screen. Put that list in the brief (see the workflow slices on
briefing language-culture).

*Observed 2026-10-31 (rust-ui-dev)*

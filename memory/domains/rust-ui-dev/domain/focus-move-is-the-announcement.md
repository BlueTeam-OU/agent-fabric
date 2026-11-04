---
role: "rust-ui-dev"
class: domain
topic: "focus-move-is-the-announcement"
description: "Screen reader: when an action moves focus to a new element whose text states the result, do not also live-announce it; then make the transient Undo findable (hint, timeout paused while focus is near, hard cap)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6e9457b36a50b10e
---

## Screen reader: when an action moves focus to a new element whose text states the result, do not also live-announce it; then make the transient Undo findable (hint, timeout paused while focus is near, hard cap)

A screen reader speaks the element that receives focus. If an action (Accept a card) moves
focus to a NEW element whose text is the result ("You saved Ada as a contact"), a live-region
announcement of the same news ("Contact saved") makes the person hear it twice. An action
whose focus stays where it was (Keep) has no new focus to speak, so there the live region is
the only voice and stays. Rule: one voice per event — focus speech when focus moves to the
result, the live region when it does not.

Dropping the announcement hides the snackbar's Undo from a screen-reader user, so the same
ruling (InterWeave contact-cards s8, #416, 2026-10-24) added three things, which apply to any
unannounced transient action:
- the focused result row carries an accessible description saying Undo exists and where it is
  in reading order ("Undo comes after all the messages in this conversation") — by reading
  order, never by visual proximity, since some states draw no neighbour (no composer when the
  network is withheld), and never "last"/"bottom", which is heard as the newest message;
- the snackbar's timeout does not run while focus is in the span from that row to the
  snackbar, restarts in full when focus leaves, stops again on return;
- a hard cap (2 minutes) closes it whatever focus does.

**How to apply:** for each action, write down which element focus lands on and what the
reader speaks there before adding any live announcement; test both with the platform's
screen reader (AT-SPI announcement events on desktop) and assert the count of utterances.

*Observed 2026-10-31 (rust-ui-dev)*

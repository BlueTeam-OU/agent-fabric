---
role: "ux-designer"
class: domain
topic: "announce-once-undo-findable"
description: "One act is announced once: when focus moves to an element that states the result, no live announcement repeats it; then the Undo the announcement no longer names gets a hint placed by reading order, not by a visual landmark"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a578946030beb923
---

## One act is announced once: when focus moves to an element that states the result, no live announcement repeats it; then the Undo the announcement no longer names gets a hint placed by reading order, not by a visual landmark

Pick the announcement by where focus goes after the act:
- focus stays on an element that already had it (Keep on a message row):
  the live region announces the result, since nothing else will;
- focus moves to a new element whose text is the result (Accept moving
  to a confirmation row): reading that element is the announcement, and
  a polite live announcement of the snackbar would say it twice.
Silencing the snackbar removes the only cue that an Undo exists, so:
- give the result element an accessible description while the Undo is
  open ("You can undo this change. Undo comes after all the messages in
  this conversation.");
- place the Undo by reading order, never by a drawn landmark: "just
  above the box where you type" pointed at nothing in a state with no
  composer, and "the bottom" is heard as the newest message;
- the snackbar's timeout does not run while focus travels from the
  result to the Undo, within the overall cap.
**Why:** InterWeave contact cards (#414, #416, 2026-10-24):
language-culture-en heard the doubled announcement; review found the
lost Undo; the landmark failed in the network-denied state.
**How to apply:** for every act with a snackbar, write the focus target
and the announcement as one row; if focus moves to the result, drop the
live announcement and add the Undo hint.
Related: [[screen-reader-text-matches-what-is-shown]], [[focus-target-not-drawn]], [[late-result-keeps-newer-feedback]]

*References: focus-target-not-drawn, late-result-keeps-newer-feedback, screen-reader-text-matches-what-is-shown*

*Observed 2026-10-25 (ux-designer)*

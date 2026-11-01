---
role: "ux-designer"
class: domain
topic: "awaited-answer-states"
description: "While an action waits for its answer: a waiting label that claims no outcome takes the button's place with focus, a progress mark that stays under reduced motion, and Back still closes the page, leaving the outcome to the next read"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0234456dd7da3403
---

## While an action waits for its answer: a waiting label that claims no outcome takes the button's place with focus, a progress mark that stays under reduced motion, and Back still closes the page, leaving the outcome to the next read

The interval between a press and its answer is a state, and an
undesigned one shows up as lost focus, a second press, or an inert Back.
- The control stays in place with focus, cannot be pressed again, and is
  labelled with a waiting text ("Adding…") announced once; where the
  controls go away, a waiting line replaces them and takes focus. The
  text claims no outcome, neither done nor failed.
- An indeterminate progress mark stays under reduced motion (it is
  status, not decoration).
- Back or Escape closes the page at once; a Back that does nothing
  breaks the platform's Back. The action goes on; its outcome is not
  shown on the closed page, counts as unknown there, and the next read
  of the list shows it.
- Inputs the action read are held read-only meanwhile.
**Why:** InterWeave add-a-peer (#385, #396, 2026-10-23): the build lost
focus when Trust's buttons went, and held Back inert during an add,
both found by review on rust-ui-dev-01's #384.
**How to apply:** for each action with an asynchronous answer, write the
waiting row (label, focus, motion, Back, inputs) beside its outcomes.
Related: [[unknown-is-not-a-default]], [[late-result-keeps-newer-feedback]], [[focus-target-not-drawn]]

*References: focus-target-not-drawn, late-result-keeps-newer-feedback, unknown-is-not-a-default*

*Observed 2026-10-25 (ux-designer)*

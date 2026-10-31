---
role: "ux-designer"
class: domain
topic: "refused-action-and-refused-undo"
description: Every action that commits through a fallible store has a refused path, and so does its Undo; a refusal arriving after the visual commit returns the item in the state the backend reports then
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5d912fd387e99ed5
---

## Every action that commits through a fallible store has a refused path, and so does its Undo; a refusal arriving after the visual commit returns the item in the state the backend reports then

"The failed state" is not one row in a spec: each action and each Undo
of it can be refused (storage degraded, a write failing), and each needs
its own outcome — what the item shows, whether feedback appears or
closes, which notice shows, where focus goes. Three traps recur:
- An Undo is itself an action and can fail. A refused Undo leaves the
  item as the action left it, closes the feedback, shows the notice.
- When the visual commit (a slide-out) does not wait for the backend,
  the refusal can arrive after the item has left the screen. The item
  then returns in the state the backend reports by then, which may
  have moved on (pending became sent), not in its pre-action state.
- Offering an Undo that cannot work (the store is already degraded,
  the session no longer holds the item) is worse than offering none:
  the spec withholds it in those states.

**Why:** in the InterWeave swipe spec (#282, #286, 2026-10-16) five
review rounds each found one of these missing: refused restore, refused
Cancel, refused Unkeep, refused Undo of Keep, a late refusal after
slide-out, a refused Cancel after the person left.

**How to apply:** list every action and every Undo in one table with
its refused outcome and its focus target, before the review does.

Related: [[late-result-keeps-newer-feedback]], [[undo-by-reverse-not-deferral]], [[focus-table-in-spec]]

*References: focus-table-in-spec, late-result-keeps-newer-feedback, undo-by-reverse-not-deferral*

*Observed 2026-10-18 (ux-designer)*

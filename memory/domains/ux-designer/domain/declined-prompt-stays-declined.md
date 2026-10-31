---
role: "ux-designer"
class: domain
topic: "declined-prompt-stays-declined"
description: A system prompt the person cancelled is not raised again by itself on a return to the app; the blocked state shows why and keeps the action that raises it in view
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a6d057e9951f2a06
---

## A system prompt the person cancelled is not raised again by itself on a return to the app; the blocked state shows why and keeps the action that raises it in view

After a person cancels an authentication (or permission) prompt:
- a return from Home or Recents, a rotation or any other continuation
  of the same screen raises nothing; only a new launch or the person's
  own action does. A return is often a glance or a copy, and re-asking
  on every switch punishes app switching and overrides their choice
  (user control and freedom);
- the resting state is never a dead end: it says what is blocked, why,
  and carries the action that raises the prompt (an Unlock in view);
- it shows nothing more than that: no error snackbar for the refused
  operation, and no promise that recovery will come unaided.
**Why:** InterWeave Android unlock flow (#309, #313, 2026-10-19/20):
the build re-prompted on every return, and an earlier state promised a
connection that never came. The architecture role ruled the same
reading into its custody record (launch = the screen's creation; an
authentication is always offered).
**How to apply:** for every prompt in a spec, write the rows "cancelled,
then return / rotate / relaunch" and "cancelled, resting state" with
the action in view and its focus target.
Related: [[strings-claim-only-what-is-true]]

*References: strings-claim-only-what-is-true*

*Observed 2026-10-22 (ux-designer)*

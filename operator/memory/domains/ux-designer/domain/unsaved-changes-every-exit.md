---
role: "ux-designer"
class: domain
topic: "unsaved-changes-every-exit"
description: "An editor's unsaved-changes question is asked by every control that closes it or puts another page in its place (list picks in a two-pane layout, notifications, identity switch, menu pages), not only Back; a control that reopens the same…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f9a4515f6466dc4f
---

## An editor's unsaved-changes question is asked by every control that closes it or puts another page in its place (list picks in a two-pane layout, notifications, identity switch, menu pages), not only Back; a control that reopens the same editor is no exit

A spec that asks "Discard changes?" on Back loses the edit silently on a
wide layout, where the list beside the editor and the app menu replace
it at once. The rule that held is stated once, by effect: any control
that closes the editor or puts another page in its place asks, including
one added later. Its edges:
- exceptions: a valid Save; an action that opens its own dialog naming
  the loss (Remove this identity), whose Cancel returns with the change;
  a control that opens this same editor (Your card with one identity);
- Continue editing changes nothing: the list's selection returns to
  where it was before the pick, focus to the control that asked (a gone
  menu item hands it to the menu's button); Enter, Escape, Back and a
  tap outside all choose it, so a second Back never drops the changes;
- Close without saving lets the asking action go on, focus where it
  would go with no unsaved change.
**Why:** InterWeave contact-cards 5.2 (#456, 2026-10-26): rust-ui-dev-02
found the loss in the wide layout; two review rounds added the exits
and exceptions.
**How to apply:** for each editor, list every control in every layout
that can replace it, by effect, and walk the list in acceptance.
Related: [[focus-target-not-drawn]]

*References: focus-target-not-drawn*

*Observed 2026-10-31 (ux-designer)*

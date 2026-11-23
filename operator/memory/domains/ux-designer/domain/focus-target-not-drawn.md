---
role: "ux-designer"
class: domain
topic: "focus-target-not-drawn"
description: "Every focus rule has a fallback for a target that is not drawn when focus arrives (removed elsewhere, the list unreadable, the controls replaced): next row by last-drawn place, else the previous, else a fixed control; announce only what…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 572a79fe9a3f984f
---

## Every focus rule has a fallback for a target that is not drawn when focus arrives (removed elsewhere, the list unreadable, the controls replaced): next row by last-drawn place, else the previous, else a fixed control; announce only what is true of what the person met

A list that another client or a later read can change makes any named
focus target (a row, its menu, "the control that opened Add") possibly
absent when focus is moved to it, or removed from under focus.
- Fallback order: the first row drawn after the target's place in the
  list as last drawn, else the last one before it, else a fixed control
  (Add). Not the first row: the person lands where they were. If the
  whole list became unreadable, the page's problem line.
- Announce (screen reader only) that the item left, before focus moves,
  when focus was on it or on any of its controls however it got there,
  or was sent to it after the person's act. Say nothing when focus never
  reached an item the app chose, and nothing for the item's own
  read-back, whose feedback already says it. The text points back to
  the item that left, not the one read next, and must be true in each
  case it covers; one case set may need two texts.
- A state changed by a read the person did not ask for (a reconnect)
  leaves focus where it is and announces the new line once as a status;
  only if the focused control itself goes does focus move, by the
  rules above.
- A press that removes its own controls (a Trust replaced by a waiting
  line) moves focus to what replaces them, made focusable.
**Why:** InterWeave add-a-peer (#385, #388, #396, 2026-10-23): five
questions from rust-ui-dev-01's build and Codex review, each a target
not drawn; the announcement text needed two keys.
**How to apply:** for each row in the spec's focus table, add "target not
drawn" and "removed from under focus" with target and announcement.
Related: [[focus-table-in-spec]], [[awaited-answer-states]]

*References: awaited-answer-states, focus-table-in-spec*

*Observed 2026-10-25 (ux-designer)*

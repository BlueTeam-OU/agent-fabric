---
role: "rust-ui-dev"
class: domain
topic: "focus-when-content-changes-under-it"
description: "Where keyboard focus goes and what a screen reader hears when a read the person did not ask for changes or removes what they are on -- next-else-previous by last drawn place, announce first, move only when the control went"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0a9641ae6b2ada35
---

## Where keyboard focus goes and what a screen reader hears when a read the person did not ask for changes or removes what they are on -- next-else-previous by last drawn place, announce first, move only when the control went

A list fed by a shared server (another administrator, a reconnect, a page reopened) changes
under the person. Rules the UX role settled across one list screen's reviews (2026-10-23), confirmed on a step page (2026-10-27), each
found as a real defect by a blind review first:
- **A row dropped while focus is on it, or on any control inside it, however focus got there**
  (Tab, pointer, or the app placing it): announce first that it is gone ("The address that was
  focused is no longer in the list"), then focus the first row drawn after it in the new list,
  else the last one before it, else the list's add action. Never the first row: the person
  lands where they were. Compute the place from the list as last drawn -- the new list no longer
  has it.
- **Focus asked for a row after the person's act** (an Undo, a step closing) and the row went
  before focus reached it: same move, a text naming the act ("...you acted on...").
- **A target the app placed but focus never reached**: move on, announce nothing -- the person
  never met it, and any text would be false.
- **A state settled by a read nobody asked for** (a lost answer decided by a later reconnect):
  focus stays; the new line is announced once as a status message. Focus moves only if the
  control it was on disappeared with the change.
- **The focused element itself is replaced** (a problem line swapped for the state line in the
  same place, drawn as two separate elements): move focus to the replacement. Reading it
  there is its one announcement; do NOT also send the status, because TalkBack reads a newly
  focused element and the status would be a second reading. Only focus on a control that
  went away (the block's Trust or Not now) moves on: next undecided block's title, else the
  page's exit.
- **That exit has to exist.** When the move target is a control that is hidden in some layouts
  (a Done shown only for two or more blocks), the decision must also make the exit appear,
  or focus drops. Check each target in every layout (one block, many) before building.
- **A note about content the person has edited away** goes silently with the edit, and does
  not come back if they edit back.

How to apply: for every list or block that a background read can change, enumerate "focus on
it / on a child / requested but not landed / elsewhere" and give each a target and an
announcement before building; test each by a read that drops or settles the item mid-focus.
Related: [[accessible-names-distinct]], [[ui-deferred-input-queue]].

*References: accessible-names-distinct, ui-deferred-input-queue*

*Observed 2026-10-27 (rust-ui-dev)*

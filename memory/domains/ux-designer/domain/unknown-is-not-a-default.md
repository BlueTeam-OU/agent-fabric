---
role: "ux-designer"
class: domain
topic: "unknown-is-not-a-default"
description: A fact the client could not read (a failed read, a lost answer, a refused read) is shown as unknown with a line saying why, never as its default value; a retry that writes nothing keeps it unknown until a read shows it
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - deade57f6fc59ac1
---

## A fact the client could not read (a failed read, a lost answer, a refused read) is shown as unknown with a line saying why, never as its default value; a retry that writes nothing keeps it unknown until a read shows it

A screen built from read data has three values for each fact, not two:
known true, known false, and not known. A build that has no "not known"
draws the default: an unread trust set drew every row "Not trusted" with
Trust offered; an unreadable list would have shown the empty-list
notice; a step after a lost Trust said "Not trusted yet". Each claim was
false for some peer.
- Unread: the row shows no state at all, and one line on the page says
  what could not be read (and Try again only where a retry can help).
  A row with no state and no line reads as "nothing wrong".
- A notice or prompt keyed on emptiness keys on a list *read* empty,
  never on one that could not be read.
- A change whose answer was lost stays unknown until a read started
  after it shows the result. A retry that fails before writing anything
  keeps the unknown text ("could not check"), never the not-written one
  ("Nothing was changed"), because the first write may have landed.
  The memory is per item (per PeerId), and what ends it is named; if
  the backend cannot promise ordering, the spec says it is best effort.
- A refused or failed *read* is not an unknown *change*: where nothing
  was asked to change, the not-written text is true.
- Every lost change counts until decided, not only the latest: a line
  left unknown stays "unsettled" until an answer stating its presence
  or a read started after it, or the page closes (#400).
- A refusal because another client changed the same thing
  ("superseded") is read back like a lost answer, never shown with the
  not-written text, and offers no Try again: a retry would quietly undo
  someone else's deliberate change. When the refusal does not prove the
  other change (an unchanged write, an eviction floor), the line says it
  "might have" changed (#425).
- A reason line is shown only when the client can know the cause; a
  status that looks like the cause (the transport's Offline, not the
  device's network) is not it (Show's no-address page, #408).
**Why:** InterWeave add-a-peer note (#380, #385, #388, 2026-10-22/23):
rust-ui-dev-01's build and Codex reviews found each of these, one class
at a time, before the rule was written once in s5.7.
**How to apply:** for every value a screen shows from a read, add the
"not read" row to the case table; for every write with a lost-answer
path, write the retry-writes-nothing row. Write the class as one rule,
not one carve-out per action.
Related: [[refused-write-read-back]], [[case-tables-keyed-by-outcome]], [[strings-claim-only-what-is-true]]

*References: case-tables-keyed-by-outcome, refused-write-read-back, strings-claim-only-what-is-true*

*Observed 2026-10-25 (ux-designer)*

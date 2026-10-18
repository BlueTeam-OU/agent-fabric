---
role: "ux-designer"
class: domain
topic: "undo-by-reverse-not-deferral"
description: When specifying a snackbar Undo for a destructive action on mobile, run the action at once and undo by the reverse action, rather than deferring it until the snackbar closes
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 22ba3ae96134d773
---

## When specifying a snackbar Undo for a destructive action on mobile, run the action at once and undo by the reverse action, rather than deferring it until the snackbar closes

On a phone the process can be killed while the undo window is open. A
deferred action then never runs, so the state after restart differs
from what the snackbar told the person ("Send cancelled", but the
message is sent; "No longer kept", but it is still kept). The rule:
after any interruption, the state is what the person last saw
confirmed. So the action runs on commit, and Undo is the reverse
action (re-keep, re-queue the same item). Defer only when no reverse
action exists, and then the deferral itself must be durable.

**Why:** in the InterWeave message-swipe spec (2026-10-16) the first
draft deferred Unkeep and Cancel. rust-ui-dev-01 found the kill case,
and the fix moved to immediate + reverse (design/2026-10-16-message-swipe.md §5).
**How to apply:** for every Undo in a spec, ask what a kill inside the
window leaves, and check that it matches the last confirmation shown.

Related: [[swipe-actions-j1]]

*References: swipe-actions-j1*

*Observed 2026-10-16 (ux-designer)*

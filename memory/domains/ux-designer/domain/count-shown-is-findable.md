---
role: "ux-designer"
class: domain
topic: "count-shown-is-findable"
description: "A count or status the person sees (an unread badge, a reply's \"earlier message\" line) follows what the person can reach, never what the model holds in memory: a memory window never hides a counted item's conversation, and rows no view can…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0538bd4c8d634d78
---

## A count or status the person sees (an unread badge, a reply's "earlier message" line) follows what the person can reach, never what the model holds in memory: a memory window never hides a counted item's conversation, and rows no view can show are reported apart, not counted

When a client bounds what it loads (a start window over a large store),
the counts it shows must still lead somewhere:
- the budget is per conversation, never global: a global budget can
  leave a conversation with unread rows out of the list while the badge
  counts them, a count the person cannot find. The list stays complete,
  from a store summary per conversation (preview, time, true count);
- a stored row that no view can ever show (undecodable) is kept out of
  the badge and the "unread above" line and reported apart (a hidden
  rows line), or the badge never clears;
- a status line about another item follows the same test: a reply's
  "In reply to an earlier message" stays true for a target released
  from memory or older than the loaded page but stored, since paging
  brings it back; "a message not shown here" only when it is neither
  held nor stored (start-window s5.2, #518; the store lookup is a gap
  carried until it can be asked by message id).
**Why:** InterWeave start window (#472, 2026-10-27), under
architect-cto's constraint that the badge counts every unread row, which
they then narrowed to every decodable one (REPLY 01a17be2).
**How to apply:** for every count in a design, name the place each
counted item can be reached from in every state (windowed, released,
undecodable, another identity), and drop or separately report what has
none.
Related: [[every-count-variant]], [[unknown-is-not-a-default]]

*References: every-count-variant, unknown-is-not-a-default*

*Observed 2026-10-31 (ux-designer)*

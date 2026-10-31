---
role: "ux-designer"
class: domain
topic: "undo-restores-identity"
description: An Undo that brings back something another system may already have seen restores the same record (its ids and bytes), never a new copy; ask the architecture role what the receiver deduplicates on
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fdb8fb1ce03a5862
---

## An Undo that brings back something another system may already have seen restores the same record (its ids and bytes), never a new copy; ask the architecture role what the receiver deduplicates on

Writing "Undo re-queues it as a new item" in a spec is a wire decision,
not wording. If the original may have reached another system (a send
cancelled while an attempt was in flight), a fresh item carries a fresh
identity, and the receiver sees a second message instead of a retry it
can deduplicate. The undo restores the record itself: every identity
and every input the system rebuilds state from (in that case the ids,
the destination, the payload bytes and the attempt count).

Two corollaries:
- Do not justify a UI bound (how long an Undo stays offered) by a
  system window that is not a guarantee (a dedup cache that evicts and
  does not survive a restart). Cap the UI on its own terms (the
  platform's longest accessibility timeout) and state the system's
  limit as the system states it.
- Which fields make the identity is the architecture role's to say.
  Ask it, with the race case, before the spec is final.

**Why:** InterWeave's swipe spec (2026-10-16): architect-cto-01 ruled
the undone cancel restores the record under both its ids, not a new row
(RETENTION.md 2, case 16), then added the attempt count after a review
found a restart would rebuild the status wrong; a later review struck
the spec's dedup-window justification for its 2-minute cap.

**How to apply:** for each Undo of a removal, ask whether anything
outside the app may have seen the item; if so, specify a restore and
send the identity question to the architecture role.

Related: [[undo-by-reverse-not-deferral]], [[refused-action-and-refused-undo]]

*References: refused-action-and-refused-undo, undo-by-reverse-not-deferral*

*Observed 2026-10-18 (ux-designer)*

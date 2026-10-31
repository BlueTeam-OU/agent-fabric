---
role: "rust-ui-dev"
class: solution
description: "an Undo of a destructive outbound action restores the deleted record (ids + stored bytes), never a re-composed copy; held in session memory only"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0dd4948597e5703
---

## an Undo of a destructive outbound action restores the deleted record (ids + stored bytes), never a re-composed copy; held in session memory only

InterWeave human client, ruled by architect-cto-01 2026-10-16 (REPLY
01a143b5, written into human-client-ui.md §6/§13 on InterWeave#284):
an Undo of Cancel send is HUMAN-CHAT.md:88's retry. Cancel runs at once
and deletes the pending row; the Undo re-commits THE SAME record --
app_message_id, transport_message_id and the stored byte-identical
payload -- durable before any attempt, then it retries as any pending
row. The record is held in process memory only while the snackbar is
up (RETENTION.md 1), dropped when it closes; no Undo once the session
copy is gone. Corrected by architect-cto-01 (INFO 01a143b9, #284 at
3a7716ed): no acceptance report reaches a cancelled row (cancel finishes
and removes it; the sender never knows whether the attempt reached), so
there is no "accepted while cancelling" edge to build; and the receiver
answers the undone retry from its dedup entry only within ADR-0019's
5-minute, never-persisted window -- past it, no exactly-once claim
(RETENTION.md 2). A TalkBack snackbar timeout is not bounded by it.
Six inputs restored unchanged (RETENTION.md 2, conformance case 16, #284
at ec8a6d84): app_message_id, transport message id, destination
selector, media type, payload bytes AND attempt count -- the client
rebuilds may_have_reached as attempts > 0 after a restart. The re-queue
is a new store entry point (the commit path mints the transport id).
A fresh id or re-encoded bytes is a second delivery or a same-key
conflict (ENDPOINTS.md §Deduplication keys on the transport id).

**Why:** the receiver dedups by transport id + payload fingerprint;
only the same record makes an undone cancel at-most-once.
**How to apply:** j82's Cancel swipe (spec b8f532da); any future undo
of a destructive outbound action takes the same shape. Related:
[[uncertain-outcome-state-and-copy]], [[peer-chosen-dedup-ids]].

*References: peer-chosen-dedup-ids, uncertain-outcome-state-and-copy*

*Observed 2026-10-16 (rust-ui-dev)*

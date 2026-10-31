---
role: "rust-ui-dev"
class: domain
topic: "peer-chosen-dedup-ids"
description: "Deduplicating received messages by a peer-chosen id -- compare content too, and never let dedup hide a row the store still holds"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fe5aecbf6f269f5a
---

## Deduplicating received messages by a peer-chosen id -- compare content too, and never let dedup hide a row the store still holds

An application message id chosen by the remote peer is not a trustworthy dedup key on its own.
- Treat a second arrival as a duplicate only when origin, id AND content (parsed envelope or
  bytes) are equal. Otherwise a peer can reuse an old id for new text, and the new text is
  silently attached to the old item, counted unread and never shown. Test: same id, different
  text, both shown.
- A dedup hit must never leave a durable store row unreachable: attach the new row to the item
  already shown (it counts in unread, viewing marks it read, a kept copy stays reachable for
  unkeep) rather than dropping it. The item shows Unread while any attached row is unread and
  Kept while any is kept.

*Observed 2026-10-15 (rust-ui-dev)*

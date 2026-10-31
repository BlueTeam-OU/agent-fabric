---
role: "p2p-network-dev"
class: solution
description: "InterWeave's ADR-0019 dedup keys on the transport MessageId, not app_message_id; an application re-send under a fresh id escapes it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f7ba0d317f8bcdbe
---

## InterWeave's ADR-0019 dedup keys on the transport MessageId, not app_message_id; an application re-send under a fresh id escapes it

In InterWeave, the receiving daemon's duplicate suppression (ADR-0019) is keyed by
(source_peer, source_endpoint, destination_selector, transport message_id). The content
fingerprint is only a conflict check on that key. The cache holds 10,000 entries for 5 minutes,
in memory only (crates/transport/runtime/src/dedup.rs). It is lost when the receiver restarts.

So any client action that re-sends "the same message" (a retry, or an Undo of Cancel) must reuse
the stored transport id AND the byte-identical payload:
- a fresh id is a new key, so the daemon enqueues a second copy;
- a re-encode under the same id is a fingerprint conflict and is rejected (ADR-0050 point 7).

Answered for rust-ui-dev-01 on 2026-10-16 (GZCoord REPLY 01a143b2-ecc9).

**Why:** clients tend to assume the remote dedups by app_message_id. Only the human client's
read_pairs does that, and only for messages already read.

**How to apply:** when asked whether a re-queue is a retry, answer from this key.

*Anchors: `crates/transport/runtime/src/dedup.rs::DEFAULT_TTL_MS`, `architecture/adr/0019-duplicate-suppression.md::message_id`*

*Observed 2026-10-16 (p2p-network-dev)*

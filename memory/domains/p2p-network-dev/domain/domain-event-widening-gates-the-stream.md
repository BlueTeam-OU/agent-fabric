---
role: "p2p-network-dev"
class: domain
topic: "domain-event-widening-gates-the-stream"
description: "Widening an EVENT shape behind a minor (a required member goes optional) must be gated per stream/session, not per message, when new-only events can coalesce with or replace old-shape ones"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 771630029ac6f785
---

## Widening an EVENT shape behind a minor (a required member goes optional) must be gated per stream/session, not per message, when new-only events can coalesce with or replace old-shape ones

InterWeave #245/#248: `previous` in the path-changed event went required → optional at IPC minor 2.4 (a
route-begin notice has none). Two things the review found:
1. The contract allowed only RESULT shapes to widen behind a minor; event shapes needed their own ruling
   (ADR-0017 A 2026-10-09: an event data shape may widen, and a required member may become optional when
   every instance omitting it is itself new behind the minor).
2. Filtering the new-only instance at emission is not enough when notices COALESCE: a pending new-only
   notice that absorbs a later change, then gets dropped for an old client, takes the change with it — the
   old client loses an event it was owed. The bound must hold on the stream: below the minor the session
   never takes a new-only instance at all (`without_route_notices` from the hello); the per-message check is
   the backstop, never the mechanism.

**How to apply:** when a minor adds a new KIND of instance to an existing event, check whether the emitter
merges, replaces or rate-limits instances; if it does, decide at session setup whether new-only instances
exist for that session. Test: an old-minor client with a change that would have merged into a new-only
notice still receives the change. Extends the drained slice "a-version-gate-has-two-sides".

*Observed 2026-10-15 (p2p-network-dev)*

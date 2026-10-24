---
role: "architect-cto"
class: domain
topic: "reflection-a-queue-after-an-acknowledgement-cannot-shed-by-dropping"
description: A queue that sits after something upstream has already acknowledged must not shed load by dropping; when full it pauses its intake and the calls that would feed it are refused locally, so before ruling any drop policy ask what upstream…
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 35d75b10bc5acc67
---

## A queue that sits after something upstream has already acknowledged must not shed load by dropping; when full it pauses its intake and the calls that would feed it are refused locally, so before ruling any drop policy ask what upstream has already acknowledged

InterWeave DECISION 01a1182e-e78d (2026-10-07): "'drop the oldest
ordinary event' would drop a direct message the transport already
acknowledged to its sender, which TRANSPORT.md section Backpressure
forbids". ADR-0002 and its history record "drops nothing, a full queue
pauses the drain" for the bridge only.

*Observed 2026-10-23 (architect-cto)*

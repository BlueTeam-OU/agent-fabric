---
role: "architect-cto"
class: domain
topic: "reflection-an-overlay-persisted-over-a-config-is-validated-composed"
description: "Configuration that validates alone need not validate once an overlay is applied, so the composed result is validated: refused at set time with nothing written, fatal at start naming the overlay, and never normalised away"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 3e733991f43a77ad
---

## Configuration that validates alone need not validate once an overlay is applied, so the composed result is validated: refused at set time with nothing written, fatal at start naming the overlay, and never normalised away

InterWeave 2026-10-11: "validation bounds the configured set, not the
composed one" (01a12997-cb1d); DECISION 01a1299f-6008: "refuse at set,
fatal at start naming the overlay, never normalised away". ADR-0028's
2026-10-11 amendment records the instance. Adds "composed state, not
each layer" to the go-live rule.

*Observed 2026-10-23 (architect-cto)*

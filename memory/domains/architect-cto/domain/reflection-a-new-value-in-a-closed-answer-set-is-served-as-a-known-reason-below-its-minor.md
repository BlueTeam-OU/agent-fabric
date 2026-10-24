---
role: "architect-cto"
class: domain
topic: "reflection-a-new-value-in-a-closed-answer-set-is-served-as-a-known-reason-below-its-minor"
description: When a minor adds a value to a closed refusal set, a client below that minor is answered a reason or error its decoder already knows, and the contract states this as a downgrade by version rather than the rule, since an older decoder…
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 47b9edd202f86127
---

## When a minor adds a value to a closed refusal set, a client below that minor is answered a reason or error its decoder already knows, and the contract states this as a downgrade by version rather than the rule, since an older decoder refuses a name it does not know

InterWeave 2026-10-23: "below 2.9 own_peer is answered grammar,
because an older client's decoder refuses a name it does not know"
(01a166dc); "LOCAL-IPC says it is a downgrade by version, not the rule"
(01a166fe); "Internal below 2.10… as it does for own_peer below 2.9"
(01a169f6). LOCAL-IPC.md states it per case; the general sentence is
written nowhere.

*Observed 2026-10-23 (architect-cto)*

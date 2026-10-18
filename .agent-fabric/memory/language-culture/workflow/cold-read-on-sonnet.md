---
role: "language-culture"
class: workflow
topic: "cold-read-on-sonnet"
description: "how a cold read is dispatched — read-only Explore on model sonnet, never opus; report a miss with its example"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9fcb059d519abb75
---

## how a cold read is dispatched — read-only Explore on model sonnet, never opus; report a miss with its example

A cold read is a fresh reader with no context who judges whether a finished text reads naturally. Dispatch it as a read-only `Explore` agent on model `sonnet`, not `opus`. The dispatch guard does not ask the owner for sonnet, and it costs about a fifth as much. The `locale-worker` (on the logins that have one) stays on opus, as agent-fabric ADR-027 designs it. This was a fabric-coordinator DECISION with the owner's word, 2026-10-10.

**Why:** every opus Explore asked the owner for approval, and the accounts were near their weekly allowance. A cold read tests comprehension and naturalness, and sonnet does this well.

**How to apply:** give the cold reader only the text, its audience and the rules it must hold. Name the model in the Supplier-Review trailer ("cold read by a fresh dispatch (sonnet) ..."). If a sonnet cold read misses something that a stronger read would have caught, send the example to fabric-coordinator. The rule changes on evidence.

*Observed 2026-10-15 (language-culture)*

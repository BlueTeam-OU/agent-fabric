---
role: "fabric-coordinator"
class: workflow
topic: "carve-out-covers-the-past"
description: "When the owner sets a direction, an exception or carve-out covers only what exists; new work follows the direction unless the exception says otherwise in words (ADR-001 rule 12)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a245664032af465b
---

## When the owner sets a direction, an exception or carve-out covers only what exists; new work follows the direction unless the exception says otherwise in words (ADR-001 rule 12)

The owner, 2026-10-09: "If a direction is set a carve out means for past." ADR-040's Wave 7 amendment (2026-10-04, my recommendation) said the control plane "stays Node" under the Python direction. The owner meant: keep the existing Node code. The fabric's sessions (python-dev and I) read it as leave to keep developing there: eight new `runtime/control/*.mjs` modules in five days, including `queue.mjs`, called from Python across the language line. The owner then chose to port the whole control plane (Wave 8).

**Why:** an exception phrased as "X stays" is ambiguous between "X is kept as is" and "X may grow"; the owner always means the first. Nobody noticed because every new module was inside the letter of the carve-out.

**How to apply:**
- When drafting an exception to a direction, write which it is: "existing code stays; new work follows the direction" by default (ADR-001 rule 12, ADR-040 rule 8).
- When reviewing or dispatching, treat new work inside a carve-out as outside the carve-out unless the exception admits new work in words; ask the owner rather than extend it.
- When an owner decision is ambiguous between the two readings, ask which one before relying on it.

*Observed 2026-10-09 (fabric-coordinator)*

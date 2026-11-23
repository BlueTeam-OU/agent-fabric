---
role: "rust-services-dev"
class: domain
topic: "ported-vectors-need-projection-mutant"
description: "Ported test vectors restated for a narrower reader can lose a case's power; mutate the reader to find which"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - e0a784772051c5f0
---

## Ported test vectors restated for a narrower reader can lose a case's power; mutate the reader to find which

When a source's test vectors are restated for a reader that sees less (the SSE
stream-end scanner reads only `event:` names, not data), a source case can tell
a defect only through the field the reader ignores. Ported framer's mid-stream
BOM case (data "c" vs "b\nc") stayed green against a scanner that strips a BOM
mid-stream; the fix was an added vector putting the BOM before an `event:` line.
How to apply: run a mutant per rule the vectors claim (here: split CRLF, data-less
dispatch, BOM never skipped, BOM skipped mid-stream) and add a vector for any
survivor. Evidence: j71, branch for/rust-services-dev-01/sse-vectors, 3214bad,
crates/protocol/core/tests/sse_vectors.rs.

*Observed 2026-11-13 (rust-services-dev)*

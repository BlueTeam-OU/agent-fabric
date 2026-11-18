---
role: "language-culture"
class: workflow
topic: "snapshot-reviewed-bytes"
description: a pass is recorded against exact bytes; keep every version read in the scratchpad, as the author overwrites in place
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bd7e2aff6980cfcb
---

## a pass is recorded against exact bytes; keep every version read in the scratchpad, as the author overwrites in place

Pass records bind to exact bytes (roles-put, j96). Authors overwrite their review files in place, so I copy every version I read into the scratchpad, keyed by sha8, before giving it to the worker. A reply always carries "pass-1 <sha>" and "pass-2 <sha>" lines. When I establish that a part is unchanged through the digest chain rather than a diff, I say so.

*References: every-charter-change-gets-two-passes*

*Observed 2026-11-09 (language-culture)*

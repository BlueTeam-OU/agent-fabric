---
role: "language-culture"
class: workflow
topic: "prompt-drift-absent-means-none"
description: "no prompt-drift line in fabric-status means no drift, not a missing line"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0a151bd23b1e58c0
---

## no prompt-drift line in fabric-status means no drift, not a missing line

fabric-status prints the prompt-drift line only on a mismatch: `prompt_drift_line` (tools/fabric/status.py:238) returns None when the launch-prompt.md sha256 matches the launched digest. When asked to quote the prompt-drift line and none is printed, the answer is "not printed: no drift", citing the function. The addenda line always prints ("store <sha> addenda commit <sha>"). Answered this way to request 01a14d86 (j65, ADR-060 stage 6, 2026-10-18).

*Observed 2026-10-18 (language-culture)*

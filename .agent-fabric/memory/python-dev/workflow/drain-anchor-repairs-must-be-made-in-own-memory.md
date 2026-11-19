---
role: "python-dev"
class: workflow
topic: "drain-anchor-repairs-must-be-made-in-own-memory"
description: "a drain that repairs an anchor in the bundle is undone by the next --all harvest unless my own memory file carries the fix"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f398456d95e57a58
---

## a drain that repairs an anchor in the bundle is undone by the next --all harvest unless my own memory file carries the fix

j99: fabric-coordinator asked me to rewrite `anchors:` in my own memory (bin/fabric-pr::basis -> tools/fabric/github/arm.py::--basis) because the harvest writes my files back.

**Why:** the bundle is derived from my store; a fix only in the bundle is lost on the next harvest.
**How to apply:** on such a REQUEST, edit the `anchors:` line in my memory file, and check the new target exists on origin/main (grep the symbol) before closing.

*Observed 2026-11-08 (python-dev)*

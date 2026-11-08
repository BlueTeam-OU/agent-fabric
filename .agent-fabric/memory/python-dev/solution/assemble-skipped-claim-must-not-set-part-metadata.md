---
role: "python-dev"
class: solution
topic: "assemble-skipped-claim-must-not-set-part-metadata"
description: write_slice derives evidence/origin/knowledge_scope from claims before the loop; a claim skipped as held in a sibling part must not feed them (j94, PR 481)
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d647655618326879
---

## write_slice derives evidence/origin/knowledge_scope from claims before the loop; a claim skipped as held in a sibling part must not feed them (j94, PR 481)

In `tools/fabric/assembler/writer.py` write_slice, `evidence`, `origin_set` and `scope` are computed from ALL group claims before the loop. j94 (PR 481) added a skip for a claim a sibling budget part already holds verbatim; the first version recomputed evidence/origin only, and the review found `knowledge_scope` still widened to `full` (second pass rewrote a domain-only part). Any new metadata derived from `claims` must be recomputed from the kept claims.

**Why:** a second pass must leave the tree unchanged; a part's labels describe what it holds.
**How to apply:** when adding a skip/continue in the claim loop, grep every value built from `claims` before the loop; the fixture must set `knowledge_scope` on the claims so assert_converged can fail. Open risk from the review: a group whose claims are all skipped and whose part file does not exist could write an empty part.

*Observed 2026-11-04 (python-dev)*

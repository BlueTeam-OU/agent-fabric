---
role: "fabric-coordinator"
class: workflow
topic: "drain-fabric-half-before-project-halves"
description: "a drain's project halves wait on the fabric half's merge — when the fabric half leaves its PR, re-block them"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 19615df9e1b7e42b
---

## a drain's project halves wait on the fabric half's merge — when the fabric half leaves its PR, re-block them

Project halves of a drain (their INDEX.md lists ../agent-fabric/memory/domains/… slices) take their fabric-ref from the merge that carries the fabric half. 2026-10-31: the fabric half was reverted out of #437, which then merged as 0c0938d4, and `fabric-jobs switch` picked j497 at once because its blocker ("merge of #437") had cleared. I re-blocked j497-j506 on job:user/j511 (the fabric half's redo) and set j511 high.

**Why:** a project half linted at a fabric ref without its slices reports every new pointer as index drift.
**How to apply:** when a drain's fabric half moves to another PR, re-block every project half on that job in the same turn. Related: [[drain-fabric-project-bundle-last]], [[j279-drain-2026-10-31-state]].

*References: drain-fabric-project-bundle-last, j279-drain-2026-10-31-state*

*Observed 2026-10-31 (fabric-coordinator)*

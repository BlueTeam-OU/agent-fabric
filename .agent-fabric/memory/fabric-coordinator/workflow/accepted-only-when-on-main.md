---
role: "fabric-coordinator"
class: workflow
topic: "accepted-only-when-on-main"
description: "Never tell agents a decision is accepted until the status change is on origin/main, or quote where the owner's word is recorded; agents hold the work while main still reads Proposed"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 34b06b661c760677
---

## Never tell agents a decision is accepted until the status change is on origin/main, or quote where the owner's word is recorded; agents hold the work while main still reads Proposed

When I broadcast decisions as accepted before the record's status flip had merged, recipients checked the tree, found "Status: Proposed", and held or doubted the work. Six agents flagged it for one record alone.

**Why:** agents verify messages against the tree (ADR-023); a broadcast ahead of the tree reads as false.
**How to apply:** merge the status change first and cite its commit in the broadcast; if it cannot merge yet, say "accepted by the owner on <date>, status change in <PR>". Related: [[rule-change-restatement-sweep]].

*References: rule-change-restatement-sweep*

*Observed 2026-10-22 (fabric-coordinator)*

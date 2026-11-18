---
role: "fabric-coordinator"
class: rationale
topic: "adr-045-move-owner-answers"
description: "the owner's 2026-11-11 answers on the operator-repository move: ADRs classified and moved/split, CI reads operator main by deploy key"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 75b59d0d4beda297
---

## the owner's 2026-11-11 answers on the operator-repository move: ADRs classified and moved/split, CI reads operator main by deploy key

The owner, 2026-11-11, on the ADR-045 extraction (docs/split/move-plan.md, j725 branch develop-qzapp/user/feat/j725-wave-3-w3-a-stage-3):

- Q1: the existing docs/adr records are classified record by record. The organisational ones move to BlueTeam-OU/blueteam-fabric with their numbers, and the engine keeps each number reserved. The owner chose this over my recommendation to keep every record in the engine. Afterwards the owner added: "you can also split adr if useful". A mixed record may therefore be split: the engine's part keeps the number, and the organisation's part becomes an operator record that cites it. Written into ADR-045 §5 rule 4 (A 2026-11-11).
- Q2: engine CI reads the operator's main for the signing check through a read-only deploy key on blueteam-fabric, held as an agent-fabric CI secret.

**Why:** the published engine must name no private content, and the signing check must stay where the commits are.
**How to apply:** the classification is its own PR, before step B; fabric-adr lookup then reads both trees. Related: [[adr-067-wave-3-started]].

*References: adr-067-wave-3-started*

*Observed 2026-11-11 (fabric-coordinator)*

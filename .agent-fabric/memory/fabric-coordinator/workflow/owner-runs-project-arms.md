---
role: "fabric-coordinator"
class: workflow
topic: "owner-runs-project-arms"
description: "A PR in a managed project (gzapp, InterWeave) under its 8-work-commit minimum: when the owner says 'arm N', give the one-line command; the owner runs it, I do not"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 575b27a1fceac07d
---

## A PR in a managed project (gzapp, InterWeave) under its 8-work-commit minimum: when the owner says 'arm N', give the one-line command; the owner runs it, I do not

2026-10-14: the owner said "arm 1117" (gzapp, 1 work commit) and rejected my own `fabric-pr arm` call, then ran the same command themselves with `!`. In agent-fabric, FleetDeck and the gateway (minimum 1) I arm at the gate myself; in a managed project, an arm "on the owner's word" is the owner's hand.

**Why:** the basis says "the owner's word"; the owner keeps that act theirs rather than relayed through me.

**How to apply:** for a project PR under its minimum, verify (review of the head, checks green, dry-run arm passes) and hand over `! cd ~/projects/<repo> && fabric-pr arm <n> --basis "the owner's word: arm <n>"`; then run `fabric-pr wait-merged <n>` in the background. Related: [[owner-arm-only-when-verified]], [[repo-transfer-owner-hand]].

*References: owner-arm-only-when-verified, repo-transfer-owner-hand*

*Anchors: `tools/fabric/github/arm.py::the owner's word`*

*Observed 2026-10-14 (fabric-coordinator)*

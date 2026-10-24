---
role: "architect-cto"
class: domain
topic: "reflection-a-revocation-survives-a-restart-at-least-as-well-as-a-grant"
description: "A revocation lasts at least as long as the grant it removes: a runtime-only admin change layered over configured state fails open at restart, silently re-allowing what a person revoked, while a lost allow fails visibly; and a…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - fd655bbfd2287b9c
---

## A revocation lasts at least as long as the grant it removes: a runtime-only admin change layered over configured state fails open at restart, silently re-allowing what a person revoked, while a lost allow fails visibly; and a safe-direction argument covers only the direction it names, so the other is stated too

InterWeave 2026-10-05..06: "a REVOCATION is undone… Nothing tells
them… The reverse is milder (an allow that vanishes fails visibly)"
(01a1123c-eb72); DECISION 01a115d9-55c1: "takes effect at the next
start, an allow as much as a revocation", correcting my own "the
conservative direction for a revocation". ADR-0028 and LOCAL-IPC.md
record the persisted overlay for this case only.

*Observed 2026-10-23 (architect-cto)*

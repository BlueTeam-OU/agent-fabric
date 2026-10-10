---
role: "fabric-coordinator"
class: rationale
topic: "rationale-carried-2026-10-01"
description: "The agent id (UUIDv7 at birth) is decided in ADR-039; stored things are named by id, typed things by login"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c43a55417dfff30c
  - df0cf2df05f10dc0
---

## The agent id (UUIDv7 at birth) is decided in ADR-039; stored things are named by id, typed things by login

Decided in agent-fabric ADR-039 (the id, minted at birth) with ADR-038 (each agent owns its key and secrets); read the records, not this section. The two earlier versions staged here (login-named stores, `store-enroll.sh --rename`) are superseded and carry no live truth.

What remains as a lesson: before making an identifier the name of anything, ask where it will be seen. What is stored is named by the id (`agent-fabric-secrets-<id>`, `<id>.asc`); what a person types or reads is the login, and a command resolves a login or an id first.

*Observed 2026-10-10 (fabric-coordinator)*

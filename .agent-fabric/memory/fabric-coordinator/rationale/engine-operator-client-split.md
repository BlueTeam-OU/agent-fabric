---
role: "fabric-coordinator"
class: rationale
topic: "engine-operator-client-split"
description: "Owner 2026-10-07 — agent-fabric splits into a public engine, Blueteam's private operator repo and per-client engagements (Gzapi first); planned, not started"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ef4b615f262f743
---

## Owner 2026-10-07 — agent-fabric splits into a public engine, Blueteam's private operator repo and per-client engagements (Gzapi first); planned, not started

The owner's decisions (2026-10-07):
- **agent-fabric becomes the public, open-source engine** (fresh history, keeps the name).
- **Blueteam** (the company running the agents) gets a private operator repository: hosts, keys, our roles, briefs, policies, memory corpus, our rulings, `clients.json`.
- **Gzapi**, the client, owns an engagement repository (its rules for agents) beside its project repos. More clients will follow.
- **All repositories stay in the gzapi-org GitHub org,** the only org with a merge queue. A repository's client comes from the operator's client list, never from the GitHub org.
- **Agents switch clients by working copy**, as context, never identity, with no relaunch.
- **Radicle becomes the forge once it has a merge-queue equivalent;** then each company may hold its own repositories.

The plan (stages 1–7, ADR-044 first) is the last section of the session plan file, appended after the earlier plans. Order: after #106, B and the own-secrets PR. Survey facts: 919 files are about 52% engine; 34 of 44 ADRs are engine and 10 mixed; never renumber; about 85 instance-data read sites.

Related: [[radicle-decentralized-forge]].

*References: radicle-decentralized-forge*

*Observed 2026-10-07 (fabric-coordinator)*

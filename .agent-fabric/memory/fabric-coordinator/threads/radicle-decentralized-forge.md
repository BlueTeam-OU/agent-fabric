---
role: "fabric-coordinator"
class: threads
topic: "radicle-decentralized-forge"
description: "the decentralized GitHub-like forge the owner has in mind is Radicle (radicle.xyz); a candidate for moving repositories off one central service"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 56cdbc1dfee73ef6
---

## the decentralized GitHub-like forge the owner has in mind is Radicle (radicle.xyz); a candidate for moving repositories off one central service

The owner confirmed on 2026-09-29 that the "github decentralized like solution" they had talked about is **Radicle**. I could not find where they first named it: my transcripts only show "repository decentralization" in their 2026-09-27 vision message ("not replacing dependence on one person with dependence on one central service").

**How Radicle works:** peer-to-peer git. Nodes replicate repositories over a gossip protocol, each identity is an Ed25519 key (a `did:key`), and patches and issues are stored in git itself.

**Why it matters here:** the per-agent secrets repositories (ADR-038) and every managed project are on GitHub today. The agent id and key (ADR-039) could map onto a Radicle node identity. No decision has been taken; it is an open thread.

**How to apply:** when repository hosting or GitHub dependence comes up, name Radicle as the owner's candidate. It is not decided. [[agent-owned-secrets-plan]] [[agent-id-uuidv7]]

*References: agent-id-uuidv7, agent-owned-secrets-plan*

*Observed 2026-09-29 (fabric-coordinator)*

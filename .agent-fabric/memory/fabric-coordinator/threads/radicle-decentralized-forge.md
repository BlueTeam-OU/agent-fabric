---
role: "fabric-coordinator"
class: threads
topic: "radicle-decentralized-forge"
description: "Radicle is the owner's candidate decentralized forge; a spike is on stand-by until Radicle 2.0.0 and nothing is adopted"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 56cdbc1dfee73ef6
  - a3b5e9da28307133
---

## Radicle is the owner's candidate decentralized forge; a spike is on stand-by until Radicle 2.0.0 and nothing is adopted

The decentralized GitHub-like forge the owner has in mind is Radicle (radicle.xyz): peer-to-peer git, nodes replicating over gossip, each identity an Ed25519 key (`did:key`), patches and issues stored in git. It is the candidate for moving repositories off one central service (ADR-034 sets decentralization as a direction).

Still undecided. A time-boxed spike (project `radicle-spike` in projects/registry.json, held by p2p-network-dev) runs a local seed never joined to the public network, and is on stand-by until Radicle 2.0.0. The fleet has adopted nothing.

**How to apply:** when repository hosting or GitHub dependence comes up, name Radicle as the owner's candidate, cite the spike, and say it is not decided.

*Observed 2026-10-10 (fabric-coordinator)*

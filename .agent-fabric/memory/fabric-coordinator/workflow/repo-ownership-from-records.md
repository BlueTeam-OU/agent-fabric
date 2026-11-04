---
role: "fabric-coordinator"
class: workflow
topic: "repo-ownership-from-records"
description: "who owns, arms or holds a repository is read from the fabric's records each time, never kept in memory"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2e8f8ee6c7757921
---

## who owns, arms or holds a repository is read from the fabric's records each time, never kept in memory

The owner, 2026-10-20: "the only source of authority for who is the owner of a repo is repo records in the fabric not the memory. in memory avoid to put something that can change like owner of a repo".

**Why:** ownership, arming authority and a repository's minimum change by commit. A memory that names them goes stale silently and then gets acted on as fact.

**How to apply:** read it at the moment of use:
- the project and its remotes: `projects/registry.json`
- which role may commit which paths: `policies/authority.json`
- who arms, and the minimum: `fabric-pr arm <n> --dry-run`, from `policies/arming.json` and the client's settings repository

A memory keeps only the decision and its reason (the owner said X on a date), and points at the record. It never keeps the current holder or list. The same goes for anything else a commit can change: account placements, pins, holders.

*Anchors: `projects/registry.json::remotes`, `policies/authority.json::contributors`, `policies/arming.json`*

*Observed 2026-10-20 (fabric-coordinator)*

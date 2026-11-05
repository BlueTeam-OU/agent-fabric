---
role: "fabric-coordinator"
class: workflow
topic: "job-project-is-registry-id"
description: "fabric-jobs add --project takes the registry id (herdr), not the GitHub repo name (agent-fabric-fleetdeck)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a3dc19a63d28f40b
---

## fabric-jobs add --project takes the registry id (herdr), not the GitHub repo name (agent-fabric-fleetdeck)

`fabric-jobs add --project agent-fabric-fleetdeck` was accepted but found no
working copy; the registry id is `herdr` (projects/registry.json). Fix with
`fabric-jobs project <id> herdr --working-copy ~/projects/herdr` (j530,
2026-11-01). Same trap for any repo renamed after its registry key.

*Observed 2026-11-01 (fabric-coordinator)*

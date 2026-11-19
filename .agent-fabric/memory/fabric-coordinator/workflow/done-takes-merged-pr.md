---
role: "fabric-coordinator"
class: workflow
topic: "done-takes-merged-pr"
description: "a PR that merged before fabric-jobs deliver ran — close the job with done <id> <owner/repo#N>, not deliver"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a13088050e5c0d73
---

## a PR that merged before fabric-jobs deliver ran — close the job with done <id> <owner/repo#N>, not deliver

Since BlueTeam-OU/agent-fabric#541 and #542 (merged 2026-11-10), `fabric-jobs done <id> <artifact>…` records the
named artifacts as evidence, so a PR merged before `deliver` closes the job with `done`; `deliver` still refuses a
merged PR as "done, not delivered". Read back live on j712 (done j712 with #541 #542, accepted). A squash-merged branch
named beside its merged PR is accepted too (#542). The ADR-037 wording for this is on my #545 (job j735).
Related: [[jobs-and-switching]]

*References: jobs-and-switching*

*Anchors: `tools/fabric/jobs.py::fabric-jobs done <id> [<artifact>...]`*

*Observed 2026-11-10 (fabric-coordinator)*

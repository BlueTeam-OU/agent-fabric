---
role: "brand-comms"
class: workflow
topic: "request-job-lands-in-senders-clone"
description: "Before starting a job queued from a REQUEST, check which project and working copy fabric-jobs filed it under: it follows the message's PROJECT, which names the sender's clone, not necessarily where the work is"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7ec77a54dd3a8b75
---

## Before starting a job queued from a REQUEST, check which project and working copy fabric-jobs filed it under: it follows the message's PROJECT, which names the sender's clone, not necessarily where the work is

A REQUEST queues a job, and fabric-jobs files it under the message's
`PROJECT:`. A sender fills that field from the clone it composes in, so
a coordinator writing from agent-fabric files a gzapp.decks job under
agent-fabric. Its working copy is then the wrong clone, and any
worktree the job cuts lands there too.

**How to apply:**
- On starting such a job, read `fabric-jobs show <id>` and compare its
  project and working copy with the repository the REQUEST's body
  names.
- If they differ, work in the right working copy, on a branch off that
  repository's default branch.
- Remove any worktree cut in the wrong clone once it holds nothing
  (`git worktree remove`, never `--force`).
- Deliver with the right repository in the artifact, written as
  `pr:<owner>/<repo>#N`. A bare `#N` doesn't resolve, and the job then
  never closes.

Related: [[publish-request-after-merges-settle]].

*References: publish-request-after-merges-settle*

*Anchors: `tools/fabric/jobsparts/records.py::meta.get("PROJECT")`*

*Observed 2026-10-24 (brand-comms)*
